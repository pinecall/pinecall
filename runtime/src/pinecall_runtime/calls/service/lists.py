"""The lists of calls and what other domains ask of the log: rows, latencies, heads, contacts."""

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.agents.declaration import AgentConfig
from pinecall_runtime.calls.facts import LINE_FIELDS, CallFacts, facts_of, line_of
from pinecall_runtime.calls.latencies import Median, medians
from pinecall_runtime.calls.logs import Logs
from pinecall_runtime.calls.models import CallLogHead
from pinecall_runtime.calls.readers import project_state
from pinecall_runtime.calls.repository.facts import (
    FactsRepository,
    Found,
    ListFilters,
    PersonaRunFilters,
    PersonaRuns,
)
from pinecall_runtime.calls.repository.heads import CallHead, HeadRepository
from pinecall_runtime.calls.repository.inbox import Inbox, InboxPage, InboxRepository
from pinecall_runtime.calls.repository.records import PhoneCall, RecordRepository
from pinecall_runtime.calls.repository.taught import TaughtRepository
from pinecall_runtime.calls.schemas import (
    CallRow,
    SessionScore,
    ThreadLast,
    ThreadMessage,
    ThreadRow,
)
from pinecall_runtime.enums import Channel, Env
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.kit.text import JsonObject
from pinecall_runtime.knowledge import service as knowledge
from pinecall_runtime.postgres import box_wide
from pinecall_runtime.wire.base import Entry
from pinecall_runtime.wire.parts import ThreadKind
from pinecall_runtime.wire.state import State, Turn

# The calls merged into one thread, newest first: each costs a log read.
CALLS_IN_A_THREAD = 20


async def find_calls(session: AsyncSession, scope: Scope, wanted: ListFilters, *, limit: int) -> Found:
    """One page of the scope's calls the filter matches, newest first, and their total."""
    return await FactsRepository(session).find(scope, wanted, limit=limit)


async def runs_of_persona(session: AsyncSession, scope: Scope, wanted: PersonaRunFilters, *, limit: int) -> PersonaRuns:
    """A page of the simulated calls the filter names, newest first, and a total."""
    return await FactsRepository(session).runs_of_persona(scope, wanted, limit=limit)


async def facts_of_calls(session: AsyncSession, calls: Sequence[str]) -> dict[str, CallFacts]:
    """The facts of each of the calls that has a row."""
    found = await FactsRepository(session).facts_of_calls(calls)
    return {call: facts_of(row) for call, (row, _) in found.items()}


# One row per call as a list draws it. A sealed call's line was written with its seal and is read
# off its facts row; a live one, or one sealed before the line existed, is folded from its log.
async def call_rows(
    session: AsyncSession, logs: Logs, calls: Sequence[str], declared: dict[str, AgentConfig | None]
) -> list[CallRow]:
    """The calls as a list shows them, the ones nothing was written to left out."""
    heads = await HeadRepository(session).among(calls)
    facts = await facts_of_calls(session, calls)
    rows: list[CallRow] = []
    for call in calls:
        head, fact = heads.get(call), facts.get(call)
        if head is None:
            continue
        line = fact.line if fact is not None and head.sealed else None
        if line is None:
            state = await logs.reading(call).snapshot()
            line = line_of(state) if state.seq else None
            line = None if line is None else {**line, **_masked(state, declared)}
        if line is None or not line.get("seq"):
            continue
        rows.append(_row(call, head, line, fact))
    return rows


def _row(call: str, head: CallLogHead, line: JsonObject, fact: CallFacts | None) -> CallRow:
    score = None
    if fact is not None and fact.judged is not None and fact.passed is not None:
        score = SessionScore(held=fact.held or 0, judged=fact.judged, passed=fact.passed, reason=fact.reason)
    return CallRow.model_validate(
        {
            **{name: line.get(name) for name in LINE_FIELDS if name != "seq"},
            "call": call,
            "agent": head.agent or "",
            "last_seq": line["seq"],
            "live": not head.sealed,
            "score": None if score is None else score.dump(),
            "flags": [] if fact is None else fact.flags,
        }
    )


# A live call's line is read through the tenant's projection, as every reader of its state is.
def _masked(state: State, declared: dict[str, AgentConfig | None]) -> JsonObject:
    projected = project_state(state, "tenant", declared.get(state.agent or ""))
    return {name: projected.get(name) for name in LINE_FIELDS if name in projected}


# The agent's last calls, each reduced: what the pipeline report says of its speed.
async def recent_latencies(session: AsyncSession, logs: Logs, slug: str, limit: int) -> tuple[int, list[Median]]:
    """How many of the agent's newest calls were read, and the medians over their turns."""
    calls = await HeadRepository(session).newest_calls(limit, agent=slug)
    turns: list[Sequence[Turn]] = []
    for call in calls:
        state = await logs.reading(call).snapshot()
        if state.seq:
            turns.append(state.turns)
    return len(turns), medians(turns)


async def newest_calls(session: AsyncSession, limit: int, *, agent: str | None = None) -> list[str]:
    """The newest calls of the box, or of one agent, across every org."""
    with box_wide():
        return await HeadRepository(session).newest_calls(limit, agent=agent)


async def newest_live_call(session: AsyncSession) -> str | None:
    """The newest call whose log is not sealed, across every org; None when every call is over."""
    with box_wide():
        return await HeadRepository(session).newest_live_call()


async def head_of_call(session: AsyncSession, call: str) -> CallHead | None:
    """Where the call was opened, or None for a call nobody wrote to or claimed."""
    return await HeadRepository(session).head_of_call(call)


# The operator's way back from a claim: an agent registered with the wrong org's key.
async def move_logs(session: AsyncSession, agent: str, org: str) -> int:
    """Move every log of the agent into the org; how many moved."""
    return await HeadRepository(session).move_logs(agent, org)


async def sealed_among(session: AsyncSession, calls: Sequence[str]) -> set[str]:
    """Which of the calls are sealed."""
    return await HeadRepository(session).sealed_among(calls)


async def ever_reached(session: AsyncSession, org: str, env: Env, contact: str) -> bool:
    """Whether the contact ever had a call with any agent of the org in the env."""
    return await InboxRepository(session).ever_reached(org, env, contact)


async def phone_calls_with(session: AsyncSession, number: str, *, since: float) -> list[PhoneCall]:
    """Every phone call with the number since then, kept or erased, oldest first."""
    return await RecordRepository(session).phone_calls_with(number, since=since)


# ── an agent's inbox ──


async def inbox_page(session: AsyncSession, inbox: Inbox, *, after: str | None, limit: int) -> InboxPage:
    """One page of the inbox, the contact that moved last first, with the unread counts."""
    return await InboxRepository(session).threads(inbox, after=after, limit=limit)


async def thread_of(session: AsyncSession, scope: Scope, slug: str, contact: str) -> list[str]:
    """The contact's newest calls with the agent, newest first; empty when there is no thread."""
    return await InboxRepository(session).calls_with(scope, slug, contact, limit=CALLS_IN_A_THREAD)


async def mark_thread_read(session: AsyncSession, inbox: Inbox, contact: str, at: float) -> None:
    """This reader has read the thread up to that moment."""
    await InboxRepository(session).mark_read(inbox, contact, at)


def thread_row(
    contact: str, name: str | None, newest: CallFacts, moved_at: float, unread: int, calls: int
) -> ThreadRow:
    """One contact of an inbox as the list shows it."""
    kind: ThreadKind = "call" if newest.spoken else ("in" if newest.last_in else "out")
    data = newest.outcome if newest.spoken else newest.last_text
    return ThreadRow(
        contact=contact,
        name=name,
        channel_last=Channel(newest.channel or Channel.web),
        last=ThreadLast(text=data, at=moved_at, kind=kind),
        unread=unread,
        calls=calls,
    )


# A written call is its turns; a spoken call is one pill with its length and whether it came up.
def thread_messages(facts: CallFacts, entries: list[Entry]) -> list[ThreadMessage]:
    """One call of a thread as its messages, or as one pill when it was spoken."""
    channel = Channel(facts.channel or Channel.web)
    if not facts.spoken:
        return [
            ThreadMessage(
                kind="in" if entry.type == "turn.user" else "out",
                text=str(entry.data.get("text") or ""),
                at=entry.ts,
                call=facts.call,
                channel=channel,
            )
            for entry in entries
            if entry.type in {"turn.user", "turn.agent"}
        ]
    ended = next((entry for entry in entries if entry.type == "call.ended"), None)
    lasted = None if ended is None else ended.data.get("duration_s")
    return [
        ThreadMessage(
            kind="call",
            text=facts.outcome,
            at=entries[0].ts if entries else 0.0,
            call=facts.call,
            channel=channel,
            duration_s=float(lasted) if isinstance(lasted, int | float) else None,
            answered=any(entry.type == "call.started" for entry in entries),
        )
    ]


# A fact is an agent's through the call that taught it, which is the log's to say.
async def facts_taught_by(
    session: AsyncSession, scope: Scope, agent: str | None, *, after: str | None, q: str | None, limit: int
) -> knowledge.FactsPage:
    """A page of the current facts the agent's calls taught, newest first; every agent's for None."""
    rows = await TaughtRepository(session).taught_by(
        scope, agent, like=knowledge.like_pattern(q), after=knowledge.parse_cursor(after), limit=limit + 1
    )
    shown = rows[:limit]
    facts = [row[0] for row in shown]
    return knowledge.FactsPage(
        facts=facts,
        next=knowledge.cursor_of(facts[-1]) if len(rows) > limit else None,
        agents={str(fact.id): str(agent_name) for fact, agent_name in shown},
    )
