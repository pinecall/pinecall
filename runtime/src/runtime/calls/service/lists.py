"""The lists of calls, and what others ask of the heads: rows, the newest, a head, the sealed, an org's logs erased."""

import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.accounts import service as accounts
from runtime.actor import THE_ORGS_OWN, Actor, Scope
from runtime.agents import service as agents
from runtime.agents.declaration import Declaration
from runtime.agents.settings import Versions
from runtime.calls.context import log_name
from runtime.calls.folds.facts import LINE_FIELDS, CallFacts, facts_of, line_of
from runtime.calls.folds.latencies import Median, medians
from runtime.calls.log.logs import Logs
from runtime.calls.models import CallLogHead
from runtime.calls.projection import TENANT, project_state
from runtime.calls.repository.entries import EntryRepository, ToolEntry
from runtime.calls.repository.facts import AgentFacts, FactsRepository
from runtime.calls.repository.heads import CallHead, Claim, HeadRepository
from runtime.calls.repository.search import ListFilters, PersonaRunFilters, PersonaRuns, SearchRepository
from runtime.calls.repository.taught import Taught, TaughtRepository
from runtime.calls.repository.unsealed import Unsealed, UnsealedRepository
from runtime.exceptions import NotFound
from runtime.kit.text import JsonObject
from runtime.scoping import box_wide
from runtime.wire.base import Entry
from runtime.wire.state import State, Turn


@dataclass(frozen=True, slots=True)
class CallPage:
    """A page of calls as a list draws them, newest first, their total and the cursor of the next page."""

    calls: list[JsonObject]
    total: int | None = None
    next: str | None = None


# What a list reads is what a call read lets through: the reader's own copy and the org's; a key
# that opens colleagues' copies, in its own, lists every copy, and in a colleague's, that one.
def list_copies(actor: Actor) -> tuple[str, ...] | None:
    """The copies a list of calls or runs reads for this key: their holders, or None for every copy."""
    person = actor.person
    if accounts.sees_every_copy(actor) and person is not None and actor.holder == person.id:
        return None
    return tuple(sorted({THE_ORGS_OWN, actor.holder}))


# One use case where the endpoint held four steps: the copies the key lists, the page, what the
# agent named declares (a live call's line is masked by it), the rows.
async def list_calls(
    session: AsyncSession,
    logs: Logs,
    actor: Actor,
    *,
    agent: str | None,
    q: str | None,
    channel: str | None,
    before: str | None,
    limit: int,
    holders: bool = False,
) -> CallPage:
    """One page of the calls of the key's scope the filter matches, newest first, one row each."""
    wanted = ListFilters(agent=agent or None, q=q or None, channel=channel, before=before, holders=list_copies(actor))
    found = await SearchRepository(session).list_calls(actor.scope, wanted, limit=limit)
    by_agent: dict[str, Declaration | None] = {}
    if wanted.agent:
        by_agent[wanted.agent] = (await agents.agent_of(session, actor.scope, wanted.agent)).declaration
    rows = await list_rows(session, logs, found.calls, by_agent, holders=holders)
    return CallPage(calls=rows, total=found.total, next=found.next)


async def list_persona_runs(
    session: AsyncSession, scope: Scope, wanted: PersonaRunFilters, *, limit: int
) -> PersonaRuns:
    """A page of the simulated calls the filter names, newest first, and a total."""
    return await SearchRepository(session).list_persona_runs(scope, wanted, limit=limit)


async def facts_of_calls(session: AsyncSession, calls: Sequence[str]) -> dict[str, CallFacts]:
    """The facts of each of the calls that has a row."""
    found = await FactsRepository(session).list_with_agent(calls)
    return {call: facts_of(kept.row) for call, kept in found.items()}


# One row per call as a list draws it. A sealed call's line was written with its seal and is read
# off its facts row; a live one, or one sealed before the line existed, is folded from its log, on
# the session that reads the page.
async def list_rows(
    session: AsyncSession,
    logs: Logs,
    calls: Sequence[str],
    by_agent: Mapping[str, Declaration | None],
    *,
    holders: bool = False,
) -> list[JsonObject]:
    """The calls as a list shows them, the ones nothing was written to left out; whose copy took each when asked."""
    heads = await HeadRepository(session).heads_of(calls)
    facts = await FactsRepository(session).list_with_agent(calls)
    names = await _name_holders(session, heads.values()) if holders else None
    rows: list[JsonObject] = []
    for call in calls:
        head, fact = heads.get(call), facts.get(call)
        if head is None:
            continue
        line = fact.row.line if fact is not None and head.sealed else None
        if line is None:
            state = await logs.reading(call).snapshot(session)
            line = {**line_of(state), **_mask(state, by_agent)} if state.seq else None
        if line is None or not line.get("seq"):
            continue
        rows.append(_row(call, head, line, fact, names))
    return rows


# The agent's last calls, each reduced: what the pipeline report says of its speed.
async def measure_latencies(session: AsyncSession, logs: Logs, slug: str, limit: int) -> tuple[int, list[Median]]:
    """How many of the agent's newest calls were read, and the medians over their turns."""
    calls = await HeadRepository(session).list_newest_calls(limit, agent=slug)
    turns: list[Sequence[Turn]] = []
    for call in calls:
        state = await logs.reading(call).snapshot(session)
        if state.seq:
            turns.append(state.turns)
    return len(turns), medians(turns)


async def find_newest_call_of(session: AsyncSession, scope: Scope, agent: str) -> str | None:
    """The scope's newest call of the agent, or None when it never had one."""
    found = await SearchRepository(session).list_calls(scope, ListFilters(agent=agent), limit=1)
    return found.calls[0] if found.calls else None


# A page of the list at a time, the calls still going left out.
async def list_newest_sealed(session: AsyncSession, scope: Scope, agent: str, most: int) -> list[str]:
    """The scope's newest finished calls of the agent, newest first, `most` at most."""
    finished: list[str] = []
    before: str | None = None
    while len(finished) < most:
        found = await SearchRepository(session).list_calls(scope, ListFilters(agent=agent, before=before), limit=most)
        sealed = await list_sealed(session, found.calls)
        finished += [call for call in found.calls if call in sealed]
        if found.next is None:
            break
        before = found.next
    return finished[:most]


async def list_newest_calls(session: AsyncSession, limit: int, *, agent: str | None = None) -> list[str]:
    """The newest calls of the box, or of one agent, across every org."""
    with box_wide():
        return await HeadRepository(session).list_newest_calls(limit, agent=agent)


async def find_newest_live_call(session: AsyncSession) -> str | None:
    """The newest call whose log is not sealed, across every org; None when every call is over."""
    with box_wide():
        return await HeadRepository(session).find_newest_live_call()


# On the session of whoever asks: a fold made again from a log (a day's drift rebuilt, a call judged
# again) reads it in the transaction it writes in.
async def list_entries(session: AsyncSession, call: str) -> list[Entry]:
    """Every durable entry of the call's log, oldest first."""
    return await EntryRepository(session).whole_of(call)


async def find_head(session: AsyncSession, call: str) -> CallHead | None:
    """Where the call was opened, or None for a call nobody wrote to or claimed."""
    return await HeadRepository(session).head_of_call(call)


# ── what the live side asks of the heads and the entries ──


# The first claim of a head stands: a call a dial placed, and one two workers open at once, is the
# first one's, whatever the second says.
async def claim_call(session: AsyncSession, call: str, agent: str, claim: Claim) -> None:
    """Record the call's scope, the versions it was built on and who opened it."""
    await HeadRepository(session).claim_call(call, agent, claim)


# Claimed and then read, never read and then claimed: until 2026-11 two orgs registering one slug
# nobody held in the same instant both passed the check, and the one that lost wrote
# `agent.registered` on the other's log. Read box-wide: another org's log reads as that org's.
async def claim_agent_log(session: AsyncSession, agent: str, org: str) -> str | None:
    """Claim the agent's own log for the org, and answer whose it is: the first claim stands."""
    heads = HeadRepository(session)
    name = log_name(None, agent)
    with box_wide():
        owner = await heads.owner_of(name)
    if owner is not None and owner != org:
        return owner
    await heads.claim_agent_log(agent, org)
    with box_wide():
        return await heads.owner_of(name)


async def list_open(session: AsyncSession, calls: Sequence[str]) -> set[str]:
    """Which of the calls have a log nobody sealed: one sealed, or erased with its head, is over."""
    heads = await HeadRepository(session).heads_of(calls)
    return {call for call, head in heads.items() if not head.sealed}


# What alerts' sweep of the newborn orgs is handed (`alerts.service.newborns.EndedCalls`).
async def list_ended_calls(session: AsyncSession, org: str) -> list[str]:
    """The org's calls that ended, in either env."""
    return await FactsRepository(session).list_ended_of_org(org)


async def count_taken(session: AsyncSession, call: str) -> int:
    """How many entries the call's log took from its writer's batches: where a writer that takes it over goes on."""
    return await HeadRepository(session).count_taken(call)


async def find_tool_entry(session: AsyncSession, call: str, kind: ToolEntry, call_id: str) -> Entry | None:
    """The `tool.call` or the `tool.result` the call's log holds for a tool call id, or None."""
    return await EntryRepository(session).find_of_tool(call, kind, call_id)


# Across every org: the reaper's questions, asked by a loop of the box.
async def list_quiet_spoken(session: AsyncSession, quiet_since: float, *, limit: int) -> list[Unsealed]:
    """The spoken or never-started calls still open and quiet since then, oldest first."""
    return await UnsealedRepository(session).list_spoken(quiet_since, limit=limit)


async def list_quiet_written(session: AsyncSession, quiet_since: float, *, limit: int) -> list[Unsealed]:
    """The written calls still open and quiet since then, with their channel."""
    return await UnsealedRepository(session).list_written(quiet_since, limit=limit)


@dataclass(frozen=True, slots=True)
class OrgsCall:
    """A call of an org as its head says it: the scope it was opened in, its agent, the versions it was built on."""

    call: str
    scope: Scope
    agent: str
    versions: Versions
    started_at: float | None


async def get_call_of_org(session: AsyncSession, org: str, call: str) -> OrgsCall:
    """The org's call by its id, as its head says it; another org's, or nobody's, is the same refusal."""
    head = await HeadRepository(session).head_of_call(call)
    if head is None or head.scope is None or head.scope.org != org:
        raise NotFound(f"no call {call} in this org")
    return OrgsCall(call, head.scope, head.agent, head.versions, head.started_at)


# The operator's way back from a claim: an agent registered with the wrong org's key.
async def move_logs(session: AsyncSession, agent: str, org: str) -> int:
    """Move every log of the agent into the org; how many moved."""
    return await HeadRepository(session).move_logs(agent, org)


async def list_sealed(session: AsyncSession, calls: Sequence[str]) -> set[str]:
    """Which of the calls are sealed."""
    return await HeadRepository(session).list_sealed(calls)


# A fact is an agent's through the call that taught it, which is the log's to say: the page is
# knowledge's to build, with its own cursor.
async def list_taught(
    session: AsyncSession,
    scope: Scope,
    agent: str | None,
    *,
    like: str | None,
    after: tuple[datetime, uuid.UUID] | None,
    limit: int,
) -> list[Taught]:
    """Current facts the agent's calls taught, newest first, each with its agent; every agent's for None."""
    return await TaughtRepository(session).list_taught(scope, agent, like=like, after=after, limit=limit)


# A copy is named by its member, read once per org the page holds; one who left keeps the id. A
# row says it only to a reader who asked: an app built before strict-parses the row it knew.
async def _name_holders(session: AsyncSession, heads: Iterable[CallLogHead]) -> dict[str, str]:
    orgs = {head.org for head in heads if head.holder and head.org}
    named: dict[str, str] = {}
    for org in orgs:
        named.update({member.id: member.name for member in await accounts.list_members(session, org)})
    return named


def _row(
    call: str, head: CallLogHead, line: JsonObject, fact: AgentFacts | None, names: Mapping[str, str] | None
) -> JsonObject:
    folded = None if fact is None else facts_of(fact.row)
    score = None
    if folded is not None and folded.judged is not None and folded.passed is not None:
        score = {"held": folded.held or 0, "judged": folded.judged, "passed": folded.passed, "reason": folded.reason}
    return {
        **{name: line.get(name) for name in LINE_FIELDS if name != "seq"},
        "call": call,
        "agent": head.agent or "",
        "last_seq": line["seq"],
        "live": not head.sealed,
        "score": score,
        "flags": [] if folded is None else folded.flags,
        **({} if names is None else {"holder": head.holder or "", "holder_name": names.get(head.holder or "")}),
    }


# A live call's line is read through the tenant's projection, as every reader of its state is.
def _mask(state: State, by_agent: Mapping[str, Declaration | None]) -> JsonObject:
    projected = project_state(state, TENANT, by_agent.get(state.agent or ""))
    return {name: projected.get(name) for name in LINE_FIELDS if name in projected}
