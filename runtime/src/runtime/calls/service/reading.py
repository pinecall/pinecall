"""A log as its reader reads it: who may, a page or a stream of it, a call's state and prompt, and the feeds."""

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.accounts import service as accounts
from runtime.actor import THE_ORGS_OWN, Actor, Scope
from runtime.agents import service as agents
from runtime.agents.declaration import Declaration
from runtime.calls.context import log_name
from runtime.calls.log.fanout import EVERYTHING, Filter, Subscription
from runtime.calls.log.feeds import Feeds
from runtime.calls.log.logs import Logs
from runtime.calls.projection import TENANT, Audience, Declaring, project_entry, project_state
from runtime.calls.repository.entries import A_PAGE, EntryRepository
from runtime.calls.repository.heads import CallHead, HeadRepository
from runtime.calls.repository.prompts import PromptRepository
from runtime.calls.service.openings import opening_of
from runtime.compliance import service as compliance
from runtime.enums import Env, KeyScope, ReadKind
from runtime.exceptions import Conflict, Forbidden, NotFound
from runtime.kit.text import JsonObject
from runtime.wire.base import Entry
from runtime.wire.events import TERMINAL_EVENT, PromptChanged
from runtime.wire.parts import Projection
from runtime.wire.room import RoomScope

NOT_YOURS = "this token reads another call"
NEVER_OPENED = "no call {call} was opened: the fleet's key reads and acts for a call once it is"
NO_SUCH_CALL = "no call {call} in this key's org and env"
STILL_GOING = "call {call} is still going: a case is made of a call that ended"
PROMPT_TAKES_A_KEY = "a call's prompt is read with a key: a token of the call reads its log, never its prompt"

# What the box says of itself belongs to no org and is sent whole; any other entry whose log
# nobody claimed yet carries no org, and is left out.
BOX_OWN = frozenset({"worker.changed"})


# ── who reads ──


# A token of one call is signed and read by the live side, above this domain: what a checked one
# says is handed in as this, and the record reads no more of it.
class Visit(Protocol):
    """What a checked token of one call says, as far as reading its log goes."""

    @property
    def call(self) -> str:
        """The call the token was minted for."""
        ...

    @property
    def scope(self) -> RoomScope:
        """What the token lets its holder do in the call."""
        ...

    @property
    def identity(self) -> str | None:
        """Who the holder is seated as in the call's room, when it is."""
        ...

    @property
    def effective_projection(self) -> Projection:
        """The projection the token reads through."""
        ...


@dataclass(frozen=True, slots=True)
class Reader:
    """Who reads a log: a key in its scope, or a token of one call."""

    actor: Actor | None = None
    visit: Visit | None = None

    @property
    def scope(self) -> Scope | None:
        """The scope a key reads in; None for a token, or the fleet, which serves every org."""
        if self.actor is None or self.actor.opens(KeyScope.fleet):
            return None
        return self.actor.scope

    @property
    def audience(self) -> Audience:
        """What the reader sees of an entry: a key the tenant's, a token its own grant's, as who it is seated as."""
        if self.visit is None:
            return TENANT
        return Audience(self.visit.effective_projection, self.visit.identity)


@dataclass(frozen=True, slots=True)
class Readable:
    """A call its reader may read: where it was opened, and the declaration it is projected by."""

    reader: Reader
    call: str
    # None for a call nobody wrote to or claimed yet: empty to a key, never another org's.
    head: CallHead | None = None
    declaration: Declaration | None = None


# A key reads a call of its org in its env; a token, its own call alone. A call nobody wrote
# yet is empty to a key, not another org's: a client that minted the id tails it before the room
# opens. The fleet's key reads only a call that was opened, of the env it serves.
async def get_readable(session: AsyncSession, reader: Reader, call: str) -> Readable:
    """The call as this reader may read it; refused when it is not theirs."""
    if reader.visit is not None and reader.visit.call != call:
        raise Forbidden(NOT_YOURS)
    kept = await HeadRepository(session).head_of_call(call)
    fleet = reader.actor is not None and reader.actor.opens(KeyScope.fleet)
    if fleet and (kept is None or kept.scope is None):
        raise NotFound(NEVER_OPENED.format(call=call))
    if kept is None:
        return Readable(reader, call)
    if not _sees(reader, kept.scope):
        raise NotFound(NO_SUCH_CALL.format(call=call))
    if reader.actor is not None:
        accounts.check_agent(reader.actor, kept.agent)
    return Readable(reader, call, kept, await _declaration_of(session, kept, call))


# A person's read and a server's are written down, by the person or the key; a visitor reads
# its own call and the fleet the call it serves, neither of which is an access to record.
async def record_read(session: AsyncSession, reader: Reader, call: str, what: ReadKind) -> None:
    """Write down who read the call, and what of it."""
    scope = reader.scope
    if reader.actor is None or scope is None:
        return
    await compliance.record_read(session, scope, call, what, by=reader.actor.asked_by)


# ── a call's log ──


@dataclass(frozen=True, slots=True)
class Asked:
    """What a reader asks of a log: above which seq, which types, only what is kept, so many a page."""

    after: int = 0
    types: str | None = None
    durable: bool = False
    limit: int = A_PAGE

    @property
    def only(self) -> Filter:
        """The filter the reader asked for."""
        return Filter.parse(self.types, durable=self.durable)


# Projected entries keep only part of the envelope, so they travel as plain JSON.
@dataclass(frozen=True, slots=True)
class LogPage:
    """One page of a log: the entries above the cursor as their reader may read them, and where the next starts."""

    entries: list[JsonObject]
    live: bool
    next: int | None


@dataclass(frozen=True, slots=True)
class Projected:
    """One entry of a stream as its reader may read it: its seq, its type, and what it says to them."""

    seq: int
    kind: str
    data: JsonObject


# The log is read on the request's session (the head for its seal and its seq, the entries for the
# page): until 2026-11 each was asked of the store, on a second connection. A stream follows the
# log on the engine's own sessions, after the request's was handed back.
async def read_call(
    session: AsyncSession,
    logs: Logs,
    sessions: async_sessionmaker[AsyncSession],
    readable: Readable,
    asked: Asked,
    *,
    follow: bool,
) -> LogPage | AsyncIterator[Projected] | None:
    """A call's entries above the cursor: a page, or a stream that ends with the call; None when it is over and read."""
    call, reader, only = readable.call, readable.reader, asked.only
    head = await HeadRepository(session).find(call)
    over = head is not None and head.sealed
    if over and asked.after >= (0 if head is None else head.seq):
        return None
    if follow:
        declaring = Declaring(readable.declaration, lambda: declaration_at_opening(sessions, call))
        entries = logs.stream(call, after=asked.after, only=only)
        return _project(entries, reader.audience, declaring, ends=True)
    read = await EntryRepository(session).page_of(call, after=asked.after, limit=asked.limit)
    return _page(read, only, reader.audience, readable.declaration, live=not over)


# An agent's own log: its registrations, what it declared, its errors. It never ends.
async def read_agent_log(
    session: AsyncSession, logs: Logs, slug: str, declaration: Declaration | None, asked: Asked, *, follow: bool
) -> LogPage | AsyncIterator[Projected]:
    """An agent's own entries above the cursor: a page, or a stream."""
    if follow:
        entries = logs.agent(slug).stream(after=asked.after, only=asked.only)
        return _project(entries, TENANT, Declaring(declaration), ends=False)
    read = await EntryRepository(session).page_of(log_name(None, slug), after=asked.after, limit=asked.limit)
    return _page(read, asked.only, TENANT, declaration, live=True)


async def declaration_at_opening(sessions: async_sessionmaker[AsyncSession], call: str) -> Declaration | None:
    """What the call opened on, read on a session of its own: for a stream that began before the call did."""
    async with sessions.begin() as session:
        opened = await opening_of(session, call)
    return None if opened is None else opened.declaration


@dataclass(frozen=True, slots=True)
class CallState:
    """A call's folded state as its reader may see it, the seq a stream resumes from, and whether it is live."""

    state: JsonObject
    last_seq: int
    live: bool


async def state_of(session: AsyncSession, logs: Logs, readable: Readable) -> CallState:
    """The call's folded state as this reader may see it, and the seq a stream resumes from."""
    state = await logs.reading(readable.call).snapshot(session)
    if state.seq == 0:
        raise NotFound(NO_SUCH_CALL.format(call=readable.call))
    return CallState(
        state=project_state(state, readable.reader.audience, readable.declaration),
        last_seq=state.seq,
        live=not await HeadRepository(session).is_sealed(readable.call),
    )


@dataclass(frozen=True, slots=True)
class PromptBlockRead:
    """One block of a call's prompt as its log names it, with the words the org kept of it."""

    seq: int
    name: str
    hash: str
    chars: int
    # None for a block no gateway kept the words of (a call from before they were kept).
    text: str | None


@dataclass(frozen=True, slots=True)
class CallPrompt:
    """Every block of prompt a call was told, in the order it was told."""

    call: str
    blocks: list[PromptBlockRead]


# A key's read alone, never a page's token: the prompt is the operator's and the app's words.
async def prompt_of(session: AsyncSession, readable: Readable) -> CallPrompt:
    """Every block of prompt the call was told, in order, each with its words when kept."""
    if readable.reader.visit is not None:
        raise Forbidden(PROMPT_TAKES_A_KEY)
    head = readable.head
    entries = await EntryRepository(session).whole_of(readable.call)
    if head is None or head.scope is None or not entries:
        raise NotFound(NO_SUCH_CALL.format(call=readable.call))
    changes = [
        (entry.seq, PromptChanged.model_validate(entry.data)) for entry in entries if entry.type == "prompt.changed"
    ]
    texts = await PromptRepository(session).texts_of(head.scope.org, sorted({block.hash for _, block in changes}))
    blocks = [
        PromptBlockRead(seq=seq, name=block.name, hash=block.hash, chars=block.chars, text=texts.get(block.hash))
        for seq, block in changes
    ]
    return CallPrompt(call=readable.call, blocks=blocks)


# ── a call that ended ──


@dataclass(frozen=True, slots=True)
class FinishedCall:
    """A call that ended, as a key that reads it finds it: its log, its agent, its env, its settings version."""

    entries: list[Entry]
    agent: str
    env: Env
    version: int | None


# What a case is promoted from, a golden derived from and a replay run on: the same reading a log's
# endpoints make (whose the call is, the agents the key's person may touch), then that it ended.
async def read_finished(session: AsyncSession, actor: Actor, call: str) -> FinishedCall:
    """A call the key reads and that ended; refused for another's call, and for one still going."""
    readable = await get_readable(session, Reader(actor=actor), call)
    entries = await EntryRepository(session).whole_of(call)
    head = readable.head
    if head is None or head.scope is None or not entries:
        raise NotFound(NO_SUCH_CALL.format(call=call))
    if not any(entry.type == "call.ended" for entry in entries):
        raise Conflict(STILL_GOING.format(call=call))
    return FinishedCall(entries=entries, agent=head.agent, env=head.scope.env, version=head.versions.settings)


# ── the feeds ──


# Live only, no cursor: every entry of the feed is also in a log, which is where to resume.
# The filter is read and the feed followed before the stream begins: a bad type is refused as a
# request is, never as a stream that ends.
async def follow_feed(feeds: Feeds, scope: Scope, types: str | None) -> AsyncIterator[Projected]:
    """The org's calls and agents changing in the scope's env, as they change; `types` keeps those alone."""
    only = Filter.parse(types, durable=False, strict=True)
    feed = await feeds.reader_of(scope.org, scope.env)
    return _project_feed(feed, only)


@dataclass(frozen=True, slots=True)
class BoxEvent:
    """One entry of some org's feed as the box's feed carries it: whose, and in which env."""

    org: str
    entry: Entry
    env: Env | None = None


# Live only, no cursor: frame ids are per-log seqs that interleave, so a reconnect starts now.
async def follow_box_feed(feeds: Feeds) -> AsyncIterator[BoxEvent]:
    """Every org's feed at once, each entry with whose it is."""
    return _name_owners(feeds, await feeds.box_reader())


# ── private ──


# A reader that leaves lets go of its feed: until 2026-11 nothing closed one, and it stayed
# followed until its queue filled.
async def _project_feed(feed: Subscription, only: Filter) -> AsyncIterator[Projected]:
    try:
        async for projected in _project(feed, TENANT, Declaring(None), ends=False, only=only):
            yield projected
    finally:
        feed.close()


async def _name_owners(feeds: Feeds, entries: Subscription) -> AsyncIterator[BoxEvent]:
    try:
        async for entry in entries:
            if entry.type in BOX_OWN:
                yield BoxEvent(org="", entry=entry)
                continue
            claimant = await feeds.claimant_of(entry)
            if claimant is not None:
                yield BoxEvent(org=claimant.org, entry=entry, env=claimant.env)
    finally:
        entries.close()


# What is public of a call is what it opened on, not what whoever holds its agent now declares: a
# call read after its app left, or in the other env, is projected by its own declaration. One
# opened before openings were kept is read by what its scope's last app declared.
async def _declaration_of(session: AsyncSession, kept: CallHead, call: str) -> Declaration | None:
    opened = await opening_of(session, call)
    if opened is not None:
        return opened.declaration
    if kept.scope is None:
        return None
    return (await agents.agent_of(session, kept.scope, kept.agent)).declaration


# The org's own calls and the reader's own scope, or every copy's to a key that opens colleagues'
# copies; a token is checked by its call, the fleet's key reads the calls of the env it serves
# and none of the other.
def _sees(reader: Reader, owner: Scope | None) -> bool:
    if reader.visit is not None:
        return True
    if reader.actor is not None and reader.actor.opens(KeyScope.fleet):
        return owner is not None and owner.env is reader.actor.env
    mine = reader.scope
    if reader.actor is None or mine is None or owner is None:
        return False
    same = mine.org == owner.org and mine.env is owner.env
    return same and (owner.holder in (THE_ORGS_OWN, mine.holder) or accounts.sees_every_copy(reader.actor))


def _page(
    read: Sequence[Entry], only: Filter, audience: Audience, declaration: Declaration | None, *, live: bool
) -> LogPage:
    kept = (project_entry(item, audience, declaration) for item in read if only.passes(item))
    # `next` is the last seq read, not kept, so a page that kept nothing still moves the cursor.
    return LogPage(entries=[item for item in kept if item is not None], live=live, next=read[-1].seq if read else None)


async def _project(
    entries: AsyncIterator[Entry], audience: Audience, declaring: Declaring, *, ends: bool, only: Filter = EVERYTHING
) -> AsyncIterator[Projected]:
    async for entry in entries:
        if not only.passes(entry):
            continue
        data = project_entry(entry, audience, await declaring.now())
        if data is not None:
            yield Projected(entry.seq, entry.type, data)
        if ends and entry.type == TERMINAL_EVENT:
            return
