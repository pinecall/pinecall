"""The calls a list asks for, a page at a time: an org's by agent, channel and words, and a persona's runs."""

from dataclasses import dataclass
from typing import Any

from sqlalchemy import Row, text

from runtime.actor import Scope
from runtime.calls.models import CallFact
from runtime.kit.repository import Repository

# The columns of call_facts, as a row that selected them all names them.
COLUMNS = tuple(CallFact.__mapper__.columns.keys())


@dataclass(frozen=True, slots=True)
class ListFilters:
    """What a call list asks for: an agent, a channel, words, and the page before this one."""

    agent: str | None = None
    # Matched case-insensitively against the call id's start, either number's digits, the
    # caller's name and the outcome.
    q: str | None = None
    channel: str | None = None
    before: str | None = None
    # The copies listed: the scope's own alone when empty, every copy of the env when None.
    holders: tuple[str, ...] | None = ()


@dataclass(frozen=True, slots=True)
class Found:
    """One page of calls, newest first, the total and the cursor of the next page."""

    calls: list[str]
    total: int
    next: str | None


@dataclass(frozen=True, slots=True)
class PersonaRunFilters:
    """Whose runs a list asks for: agents, a persona, the page before; none named is every run."""

    agent: str | None = None
    persona: str | None = None
    before: str | None = None
    agents: tuple[str, ...] = ()
    # One simulated call by its id.
    call: str | None = None
    # The calls of one comparison, by its id.
    comparison: str | None = None
    # The copies read: the scope's own alone when empty, every copy of the env when None.
    holders: tuple[str, ...] | None = ()


@dataclass(frozen=True, slots=True)
class PersonaRun:
    """One simulated call by a persona: when it started, and its facts with their agent."""

    started_at: float
    agent: str
    facts: CallFact


@dataclass(frozen=True, slots=True)
class PersonaRuns:
    """One page of a persona's runs, newest first, the total and the cursor of the next page."""

    runs: list[PersonaRun]
    total: int
    next: str | None


# words is an escaped LIKE pattern and digits its digits; a call with no facts row still matches
# a filter on the agent alone. holders null is every copy of the env.
MATCHING = """
from call_log_head head left join call_facts f on f.call = head.log
where head.org = :org and head.call is not null
  and head.env = :env
  and (cast(:holders as text[]) is null or head.holder = any(cast(:holders as text[])))
  and (cast(:agent as text) is null or head.agent = :agent)
  and (cast(:channel as text) is null or f.channel = :channel)
  and (cast(:words as text) is null
       or lower(head.log) like lower(:words) || '%'
       or (cast(:digits as text) <> '' and (regexp_replace(coalesce(f.from_number, ''), '\\D', '', 'g')
                                   like '%' || :digits || '%'
                              or regexp_replace(coalesce(f.to_number, ''), '\\D', '', 'g')
                                   like '%' || :digits || '%'))
       or f.name ilike '%' || :words || '%'
       or f.outcome ilike '%' || :words || '%')
"""

# The page before this one is the cursor: a call id, whose start time and id bound the page.
A_PAGE_BEFORE = """
  and (cast(:before as text) is null or (coalesce(head.started_at, -1), head.log) < (
        select coalesce(before.started_at, -1), before.log
        from call_log_head before where before.log = :before))
order by coalesce(head.started_at, -1) desc, head.log desc
limit :limit
"""

# A persona's runs to one agent, the runs to the agents named, or, none named, every simulated
# call of the copies read; holders null is every copy of the env.
THE_PERSONAS_RUNS = """
from call_log_head head join call_facts f on f.call = head.log
where head.org = :org and head.env = :env
  and (cast(:holders as text[]) is null or head.holder = any(cast(:holders as text[])))
  and head.call is not null and (f.persona is not null or f.comparison is not null)
  and (cast(:agent as text) is null or head.agent = :agent)
  and (cardinality(cast(:agents as text[])) = 0 or head.agent = any(cast(:agents as text[])))
  and (cast(:persona as text) is null or f.persona = :persona)
  and (cast(:call as text) is null or head.log = :call)
  and (cast(:comparison as text) is null or f.comparison = :comparison)
"""

FOUND_COUNT = text("select count(*) as total " + MATCHING)
FOUND_PAGE = text("select head.log as call " + MATCHING + A_PAGE_BEFORE)
PERSONA_RUNS_COUNT = text("select count(*) as total " + THE_PERSONAS_RUNS)
PERSONA_RUNS_PAGE = text(
    "select f.*, head.agent, coalesce(head.started_at, -1) as started_at " + THE_PERSONAS_RUNS + A_PAGE_BEFORE
)


def facts_of_row(row: Row[Any]) -> CallFact:
    """A CallFact built off a row that selected call_facts' columns by name."""
    return CallFact(**{name: getattr(row, name) for name in COLUMNS})


class SearchRepository(Repository[CallFact]):
    """The calls of a scope as its lists page through them, read off the heads and the facts."""

    model = CallFact

    async def list_calls(self, scope: Scope, wanted: ListFilters, *, limit: int) -> Found:
        """One page of the scope's calls the filter matches, newest first, and their total."""
        params = {
            "org": scope.org,
            "env": scope.env.value,
            "holders": _holders(scope, wanted.holders),
            "agent": wanted.agent,
            "channel": wanted.channel,
            "words": None if wanted.q is None else _escape_like(wanted.q),
            "digits": "".join(item for item in (wanted.q or "") if item.isdigit()),
        }
        total = (await self.session.execute(FOUND_COUNT, params)).scalar_one()
        page = {**params, "before": wanted.before, "limit": limit + 1}
        calls = [str(row.call) for row in (await self.session.execute(FOUND_PAGE, page)).all()]
        return Found(calls=calls[:limit], total=int(total), next=calls[limit - 1] if len(calls) > limit else None)

    async def list_persona_runs(self, scope: Scope, wanted: PersonaRunFilters, *, limit: int) -> PersonaRuns:
        """A page of the simulated calls the filter names, newest first, and a total."""
        params = {
            "org": scope.org,
            "env": scope.env.value,
            "holders": _holders(scope, wanted.holders),
            "agent": wanted.agent,
            "agents": list(wanted.agents),
            "persona": wanted.persona,
            "call": wanted.call,
            "comparison": wanted.comparison,
        }
        total = (await self.session.execute(PERSONA_RUNS_COUNT, params)).scalar_one()
        page = {**params, "before": wanted.before, "limit": limit + 1}
        rows = (await self.session.execute(PERSONA_RUNS_PAGE, page)).all()
        runs = [PersonaRun(float(row.started_at), str(row.agent), facts_of_row(row)) for row in rows]
        return PersonaRuns(
            runs=runs[:limit], total=int(total), next=runs[limit - 1].facts.call if len(runs) > limit else None
        )


def _holders(scope: Scope, holders: tuple[str, ...] | None) -> list[str] | None:
    return None if holders is None else list(holders or (scope.holder,))


def _escape_like(words: str) -> str:
    return words.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
