"""An agent's inbox by contact: its threads, one thread's calls merged, what a reader has read."""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.actor import Actor, Scope
from runtime.calls.folds.facts import CallFacts, facts_of
from runtime.calls.repository.entries import EntryRepository
from runtime.calls.repository.facts import FactsRepository
from runtime.calls.repository.inbox import Inbox, InboxRepository
from runtime.enums import Channel, Env
from runtime.exceptions import NotFound
from runtime.kit.time import epoch
from runtime.scoping import box_wide
from runtime.wire.base import Entry
from runtime.wire.parts import ThreadKind

# The calls merged into one thread, newest first: each costs a log read.
CALLS_IN_A_THREAD = 20


@dataclass(frozen=True, slots=True)
class ThreadLast:
    """The newest thing on a contact's thread."""

    text: str | None
    at: float
    kind: ThreadKind


@dataclass(frozen=True, slots=True)
class Thread:
    """One contact of an agent's inbox: every call of theirs, folded into one line."""

    contact: str
    name: str | None
    channel_last: Channel
    last: ThreadLast
    unread: int
    calls: int


@dataclass(frozen=True, slots=True)
class ThreadPage:
    """One page of an inbox, the contact that moved last first, and the cursor of the next."""

    threads: list[Thread]
    next: str | None


@dataclass(frozen=True, slots=True)
class ThreadMessage:
    """One message of a thread, or one spoken call drawn as a pill."""

    kind: ThreadKind
    text: str | None
    at: float
    call: str
    channel: Channel
    duration_s: float | None = None
    answered: bool | None = None


@dataclass(frozen=True, slots=True)
class ContactThread:
    """Every call of one contact with an agent, merged, oldest first."""

    contact: str
    name: str | None
    messages: list[ThreadMessage]


# The read cursor is the person's; a server's key keeps its own.
async def list_threads(session: AsyncSession, actor: Actor, slug: str, *, after: str | None, limit: int) -> ThreadPage:
    """The agent's contacts, the one that moved last first, with what this reader has not read."""
    inbox = Inbox(actor.scope, slug, actor.asked_by)
    found = await InboxRepository(session).list_threads(inbox, after=after, limit=limit)
    threads = [
        _thread(row.contact, row.name, facts_of(row.newest), row.moved_at, row.unread, row.calls) for row in found.rows
    ]
    return ThreadPage(threads=threads, next=found.next)


async def list_calls_with(session: AsyncSession, scope: Scope, slug: str, contact: str) -> list[str]:
    """The contact's newest calls with the agent, newest first; refused when there is no thread."""
    calls = await InboxRepository(session).list_calls_with(scope, slug, contact, limit=CALLS_IN_A_THREAD)
    if not calls:
        raise NotFound(f"no thread with {contact} on agent {slug} in this scope")
    return calls


# What a conversation that comes back asks: a WhatsApp thread is taken up again on its newest call.
async def find_newest_call_with(session: AsyncSession, scope: Scope, slug: str, contact: str) -> str | None:
    """The contact's newest call with the agent, or None when they never spoke."""
    newest = await InboxRepository(session).list_calls_with(scope, slug, contact, limit=1)
    return newest[0] if newest else None


# Each call's log is read on the session that read the thread: until 2026-11 each was asked of the
# store, a second connection twenty times over.
async def thread_of(session: AsyncSession, scope: Scope, slug: str, contact: str) -> ContactThread:
    """A contact's calls with the agent merged into one thread, oldest first."""
    calls = await list_calls_with(session, scope, slug, contact)
    kept = await FactsRepository(session).list_with_agent(calls)
    facts = {call: facts_of(found.row) for call, found in kept.items()}
    messages: list[ThreadMessage] = []
    for call in reversed(calls):
        if call in facts:
            messages += _messages_of(facts[call], await EntryRepository(session).whole_of(call))
    name = next((facts[call].name for call in calls if call in facts and facts[call].name), None)
    return ContactThread(contact=contact, name=name, messages=messages)


async def mark_read(session: AsyncSession, actor: Actor, slug: str, contact: str) -> None:
    """This reader has read the thread up to now."""
    await list_calls_with(session, actor.scope, slug, contact)
    await InboxRepository(session).mark_read(Inbox(actor.scope, slug, actor.asked_by), contact, epoch())


async def has_reached(session: AsyncSession, org: str, env: Env, contact: str) -> bool:
    """Whether the contact ever had a call with any agent of the org in the env."""
    return await InboxRepository(session).has_reached(org, env, contact)


# `thread_reads` names its org with no key to it, so nothing cascades: retention calls this when an
# org is erased.
async def delete_reads(session: AsyncSession, org: str) -> int:
    """Delete every reader's cursor of the org; how many went."""
    with box_wide():
        return await InboxRepository(session).delete_of_org(org)


def _thread(contact: str, name: str | None, newest: CallFacts, moved_at: float, unread: int, calls: int) -> Thread:
    kind: ThreadKind = "call" if newest.spoken else ("in" if newest.last_in else "out")
    said = newest.outcome if newest.spoken else newest.last_text
    return Thread(
        contact=contact,
        name=name,
        channel_last=Channel(newest.channel or Channel.web),
        last=ThreadLast(text=said, at=moved_at, kind=kind),
        unread=unread,
        calls=calls,
    )


# A written call is its turns; a spoken call is one pill with its length and whether it came up.
def _messages_of(facts: CallFacts, entries: list[Entry]) -> list[ThreadMessage]:
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
