"""The call_facts rows: locked and rewritten by the writer, read by the lists and the inbox."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Row, func, select, text
from sqlalchemy.dialects.postgresql import insert

from pinecall_runtime.calls.models import CallFact, CallLogHead
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.kit.repository import Repository

# The columns of call_facts, in the order the row is written.
COLUMNS = tuple(column.name for column in CallFact.__table__.columns)


@dataclass(frozen=True, slots=True)
class ListFilters:
    """What a call list asks for: an agent, a channel, words, and the page before this one."""

    agent: str | None = None
    # Matched case-insensitively against the call id's start, either number's digits, the
    # caller's name and the outcome.
    q: str | None = None
    channel: str | None = None
    before: str | None = None


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
# a filter on the agent alone.
MATCHING = """
from call_log_head head left join call_facts f on f.call = head.log
where head.org = :org and head.call is not null
  and head.env = :env and head.holder = :holder
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
# call of the scope.
THE_PERSONAS_RUNS = """
from call_log_head head join call_facts f on f.call = head.log
where head.org = :org and head.env = :env and head.holder = :holder
  and head.call is not null and f.persona is not null
  and (cast(:agent as text) is null or head.agent = :agent)
  and (cardinality(cast(:agents as text[])) = 0 or head.agent = any(cast(:agents as text[])))
  and (cast(:persona as text) is null or f.persona = :persona)
"""

FOUND_COUNT = text("select count(*) as total " + MATCHING)
FOUND_PAGE = text("select head.log as call " + MATCHING + A_PAGE_BEFORE)
PERSONA_RUNS_COUNT = text("select count(*) as total " + THE_PERSONAS_RUNS)
PERSONA_RUNS_PAGE = text(
    "select f.*, head.agent, coalesce(head.started_at, -1) as started_at " + THE_PERSONAS_RUNS + A_PAGE_BEFORE
)


class FactsRepository(Repository[CallFact]):
    """What is known of every call without folding its log."""

    model = CallFact

    # In the order of the calls, as the heads are locked: two writers never wait in a circle.
    async def lock(self, calls: Sequence[str]) -> dict[str, CallFact]:
        """The facts rows of these calls, locked for the writer's transaction."""
        statement = self.statement().where(CallFact.call.in_(list(calls))).order_by(CallFact.call).with_for_update()
        return {row.call: row for row in await self.all(statement)}

    # The whole row is written every time: the merge happened in the fold, in one place.
    async def write_all(self, rows: Sequence[Mapping[str, Any]]) -> None:
        """Insert or replace each row whole."""
        if not rows:
            return
        statement = insert(CallFact)
        updates = {name: getattr(statement.excluded, name) for name in COLUMNS if name != "call"}
        await self.session.execute(
            statement.on_conflict_do_update(index_elements=[CallFact.call], set_=updates), list(rows)
        )

    # Not a fold: the vendors a call ran on the box's key are not in its entries, the gateway
    # knows them at the seal.
    async def set_lent(self, call: str, vendors: Sequence[str]) -> None:
        """Keep the vendors the call ran on the box's own key with its facts."""
        statement = insert(CallFact).values(call=call, lent=list(vendors))
        statement = statement.on_conflict_do_update(
            index_elements=[CallFact.call], set_={"lent": statement.excluded.lent}
        )
        await self.session.execute(statement)

    async def lent_of(self, calls: Sequence[str]) -> dict[str, tuple[str, ...]]:
        """The vendors each of the calls ran on the box's own key, for the calls that ran on any."""
        if not calls:
            return {}
        statement = select(CallFact.call, CallFact.lent).where(
            CallFact.call.in_(list(calls)), func.cardinality(CallFact.lent) > 0
        )
        return {call: tuple(lent) for call, lent in (await self.session.execute(statement)).all()}

    # Not a fold: the state's line at the seal, kept so a list reads it instead of folding the log.
    async def set_line(self, call: str, line: Mapping[str, Any]) -> None:
        """Keep what a list shows of the call with its facts."""
        statement = insert(CallFact).values(call=call, line=dict(line))
        statement = statement.on_conflict_do_update(
            index_elements=[CallFact.call], set_={"line": statement.excluded.line}
        )
        await self.session.execute(statement)

    async def get(self, call: str) -> CallFact | None:
        """The facts of one call, or None while nothing folded into them."""
        return await self.one_or_none(self.statement().where(CallFact.call == call))

    async def facts_of_calls(self, calls: Sequence[str]) -> dict[str, tuple[CallFact, str]]:
        """The facts of each of the calls that has a row, with its agent off the head."""
        if not calls:
            return {}
        statement = (
            select(CallFact, CallLogHead.agent)
            .join(CallLogHead, CallLogHead.log == CallFact.call)
            .where(CallFact.call.in_(list(calls)))
        )
        rows = (await self.session.execute(statement)).all()
        return {row[0].call: (row[0], row[1] or "") for row in rows}

    async def find(self, scope: Scope, wanted: ListFilters, *, limit: int) -> Found:
        """One page of the scope's calls the filter matches, newest first, and their total."""
        params = {
            "org": scope.org,
            "env": scope.env.value,
            "holder": scope.holder,
            "agent": wanted.agent,
            "channel": wanted.channel,
            "words": None if wanted.q is None else _like_escaped(wanted.q),
            "digits": "".join(item for item in (wanted.q or "") if item.isdigit()),
        }
        total = (await self.session.execute(FOUND_COUNT, params)).scalar_one()
        page = {**params, "before": wanted.before, "limit": limit + 1}
        calls = [str(row.call) for row in (await self.session.execute(FOUND_PAGE, page)).all()]
        return Found(calls=calls[:limit], total=int(total), next=calls[limit - 1] if len(calls) > limit else None)

    async def runs_of_persona(self, scope: Scope, wanted: PersonaRunFilters, *, limit: int) -> PersonaRuns:
        """A page of the simulated calls the filter names, newest first, and a total."""
        params = {
            "org": scope.org,
            "env": scope.env.value,
            "holder": scope.holder,
            "agent": wanted.agent,
            "agents": list(wanted.agents),
            "persona": wanted.persona,
        }
        total = (await self.session.execute(PERSONA_RUNS_COUNT, params)).scalar_one()
        page = {**params, "before": wanted.before, "limit": limit + 1}
        rows = (await self.session.execute(PERSONA_RUNS_PAGE, page)).all()
        runs = [PersonaRun(float(row.started_at), str(row.agent), facts_of_row(row)) for row in rows]
        return PersonaRuns(
            runs=runs[:limit], total=int(total), next=runs[limit - 1].facts.call if len(runs) > limit else None
        )


def facts_of_row(row: Row[Any]) -> CallFact:
    """A CallFact built off a row that selected call_facts' columns by name."""
    return CallFact(**{name: getattr(row, name) for name in COLUMNS})


def _like_escaped(words: str) -> str:
    return words.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
