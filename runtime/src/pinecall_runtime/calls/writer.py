"""The writer: every log's appends written a group per transaction, fed ones in a lane apart."""

import asyncio
import logging
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinecall_runtime.calls.facts import record
from pinecall_runtime.calls.repository.writes import Head, WriteRepository
from pinecall_runtime.exceptions import Conflict
from pinecall_runtime.kit.text import JsonObject
from pinecall_runtime.postgres import box_task
from pinecall_runtime.wire.base import Entry

logger = logging.getLogger(__name__)

# The most entries one group carries.
MOST_IN_A_GROUP = 500

# The only metered types. Usage is a projection of the log, never stored beside it.
METERED_TYPES = ("call.summary", "call.score", "evals.spent")

# The types read across every log by position: the usage feed, the callbacks, the codes, and
# WhatsApp's queue. A position is given at insert, not at commit, so a transaction that writes one
# of these takes the feed's lock first and holds it to its commit: their positions come in commit
# order, and a reader whose cursor passed one has seen every one before it.
FED_TYPES = frozenset(
    {*METERED_TYPES, "code.issued", "code.claimed", "callback.requested", "message.waiting", "message.taken"}
)

# A request that writes a fed type goes in the fed lane, which alone takes the feed's lock; every
# other goes in the plain lane, which never waits on it.
type Lane = Literal["fed", "plain"]
LANES: tuple[Lane, ...] = ("fed", "plain")

# The gateway's own entry, a worker's batch, a verdict written again on a sealed log, or a durable
# entry written only when its log is open and holds none of its type.
type Kind = Literal["entry", "batch", "score", "first", "answer"]


@dataclass(frozen=True, slots=True)
class Unnumbered:
    """An entry the log has not numbered yet: what it is, whether a store keeps it, and when."""

    type: str
    data: JsonObject
    ephemeral: bool
    ts: float


@dataclass(frozen=True, slots=True)
class Batch:
    """A request's entries as the log numbered them, and whether the log had taken them before."""

    entries: list[Entry]
    replayed: bool


@dataclass(frozen=True, slots=True)
class Append:
    """One request to the writer: its kind, its log, its entries stamped, and a batch's `after`."""

    kind: Kind
    log: str
    call: str | None
    agent: str
    entries: Sequence[Unnumbered]
    after: int = 0


@dataclass(frozen=True, slots=True)
class _Queued:
    append: Append
    lane: Lane
    answer: asyncio.Future[Batch]


@dataclass(frozen=True, slots=True)
class _Moved:
    """A request the log takes: its head as it will be, and the first seq of its entries."""

    first: int
    seq: int
    written: int
    written_seq: int | None


# What a first-of-its-type request is answered with when its log did not need it.
NOT_NEEDED = Batch(entries=[], replayed=False)


class Writer:
    """The appends not yet written, in the order they came, and a task per lane writing them."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        """Keep the sessions; a lane's task starts with its first request and ends when none is left."""
        self.sessions = sessions
        self._queue: deque[_Queued] = deque()
        # The logs a lane's transaction writes now: the other lane leaves them until it commits.
        self._writing: set[str] = set()
        self._tasks: dict[Lane, asyncio.Task[None]] = {}

    @property
    def waiting(self) -> int:
        """How many requests wait for a transaction now: what /metrics says a writer is behind."""
        return len(self._queue)

    async def write(self, append: Append) -> Batch:
        """Queue the request; its entries numbered, once the transaction that wrote them commits."""
        answer: asyncio.Future[Batch] = asyncio.get_running_loop().create_future()
        self._queue.append(_Queued(append, "fed" if _fed(append) else "plain", answer))
        self._start_lanes()
        return await answer

    async def drain(self) -> None:
        """Return once every request queued so far is written and answered."""
        while running := [task for task in self._tasks.values() if not task.done()]:
            await asyncio.shield(asyncio.gather(*running))

    # A lane idle with a request of its own waiting starts: on a request, and whenever a group
    # ends, since the other lane may have been waiting on its logs.
    def _start_lanes(self) -> None:
        for lane in LANES:
            task = self._tasks.get(lane)
            idle = task is None or task.done()
            if idle and any(queued.lane == lane for queued in self._queue):
                self._tasks[lane] = box_task(self._run_lane(lane))

    # No timer: what arrives while a transaction is out is the next group. A lane ends when it has
    # nothing it may write; the other lane starts it again when it lets a log go.
    async def _run_lane(self, lane: Lane) -> None:
        while group := self._take(lane):
            logs = {queued.append.log for queued in group}
            self._writing |= logs
            try:
                await self._settle(group)
            finally:
                self._writing -= logs
                self._start_lanes()

    # A log is in a group once, and never while the other lane writes it or holds an earlier
    # request of it: its later requests, and every one past the group's size, wait in the order
    # they came. A request its caller gave up on is not written.
    def _take(self, lane: Lane) -> list[_Queued]:
        group: list[_Queued] = []
        later: deque[_Queued] = deque()
        logs = set(self._writing)
        size = 0
        while self._queue:
            queued = self._queue.popleft()
            if queued.answer.done():
                continue
            entries = len(queued.append.entries)
            fits = not group or size + entries <= MOST_IN_A_GROUP
            if queued.lane == lane and queued.append.log not in logs and fits:
                group.append(queued)
                size += entries
            else:
                later.append(queued)
            logs.add(queued.append.log)
        self._queue = later
        return group

    # A member whose own entries break the transaction (a constraint, bytes Postgres refuses)
    # would take the group down with it, so the group is written again a member at a time and
    # only that one is refused. Anything else (the pool, the network) is every member's answer.
    async def _settle(self, group: list[_Queued]) -> None:
        try:
            outcomes = await self._transaction([queued.append for queued in group])
        except (IntegrityError, DataError):
            logger.warning("a group of %d broke; each is written alone", len(group), exc_info=True)
            for queued in group:
                await self._alone(queued)
            return
        except Exception as broke:
            logger.warning("a group of %d was not written", len(group), exc_info=True)
            for queued in group:
                _answer(queued.answer, broke)
            return
        for queued, outcome in zip(group, outcomes, strict=True):
            _answer(queued.answer, outcome)

    async def _alone(self, queued: _Queued) -> None:
        try:
            [outcome] = await self._transaction([queued.append])
        except Exception as broke:
            logger.warning("an append to %s was refused", queued.append.log, exc_info=True)
            _answer(queued.answer, broke)
            return
        _answer(queued.answer, outcome)

    # Every statement covers the whole group: the heads begun, locked, read and moved at once,
    # the rows written at once, the facts folded at once. The answers are known before the commit
    # and handed out only after it.
    async def _transaction(self, group: Sequence[Append]) -> list[Batch | Conflict]:
        begun = [append for append in group if append.kind == "entry" or (append.kind == "batch" and append.after == 0)]
        async with self.sessions.begin() as session:
            writes = WriteRepository(session)
            if any(_fed(append) for append in group):
                await writes.take_feed_order()
            heads = await writes.lock_heads([append.log for append in group])
            missing = [append for append in begun if append.log not in heads]
            if missing:
                heads |= await writes.begin_heads(
                    [append.log for append in missing],
                    [append.agent for append in missing],
                    [append.call for append in missing],
                )
            firsts = [append for append in group if append.kind == "first"]
            answers = [append for append in group if append.kind == "answer"]
            typed = await writes.held_types(
                [append.log for append in firsts], [append.entries[0].type for append in firsts]
            )
            typed |= await writes.unanswerable(
                [append.log for append in answers], [str(append.entries[0].data.get("call_id")) for append in answers]
            )
            outcomes = [_outcome_of(append, heads.get(append.log), typed) for append in group]
            moved = [
                (append, outcome)
                for append, outcome in zip(group, outcomes, strict=True)
                if isinstance(outcome, _Moved)
            ]
            numbered = [_numbered(append, first=outcome.first) for append, outcome in moved]
            entries = [entry for batch in numbered for entry in batch]
            if moved:
                await writes.write(_heads_moved(moved), _rows(entries))
            await record(session, entries)
        taken = iter(numbered)
        return [
            Batch(entries=next(taken), replayed=False) if isinstance(outcome, _Moved) else outcome
            for outcome in outcomes
        ]


def _fed(append: Append) -> bool:
    return any(not item.ephemeral and item.type in FED_TYPES for item in append.entries)


# A first-of-its-type request is not needed on a log never written, sealed, or holding its type;
# an answer, on one that never asked its call id or holds its answer already.
def _outcome_of(append: Append, head: Head | None, typed: set[str]) -> _Moved | Batch | Conflict:
    guarded = append.kind in {"first", "answer"}
    if guarded and (append.log in typed or head is None or head.sealed):
        return NOT_NEEDED
    return _outcome(append, head)


def _outcome(append: Append, head: Head | None) -> _Moved | Batch | Conflict:
    if head is None and append.kind == "score":
        return Conflict(f"call {append.call} has no log to judge")
    if append.kind == "entry" and (head is None or head.sealed):
        return Conflict(f"call {append.call} has ended: {append.entries[0].type} cannot be appended")
    if head is not None and append.kind != "batch":
        seq = head.seq + 1
        return _Moved(first=seq, seq=seq, written=head.written, written_seq=head.written_seq)
    n = len(append.entries)
    if head is not None and not head.sealed and head.written == append.after:
        seq = head.seq + n
        return _Moved(first=seq - n + 1, seq=seq, written=append.after + n, written_seq=seq)
    first = _replayed_from(append, head)
    if isinstance(first, Conflict):
        return first
    return Batch(entries=_numbered(append, first=first), replayed=True)


# A retry of a batch the log took is answered even after the seal, so the replay is asked first.
def _replayed_from(append: Append, head: Head | None) -> int | Conflict:
    n, after = len(append.entries), append.after
    written = 0 if head is None else head.written
    last = None if head is None else head.written_seq
    if after + n == written and last is not None:
        return last - n + 1
    if head is not None and head.sealed:
        return Conflict(f"call {append.call} has ended: its batch cannot be appended")
    return Conflict(
        f"call {append.call}: the log took {written} entries from its worker, and the batch says {after} before its {n}"
    )


def _numbered(append: Append, *, first: int) -> list[Entry]:
    return [
        Entry(
            seq=seq,
            ts=item.ts,
            call=append.call,
            agent=append.agent,
            type=item.type,
            ephemeral=item.ephemeral,
            data=item.data,
        )
        for seq, item in enumerate(append.entries, first)
    ]


# A verdict on a sealed log names nothing of the log: it only takes the next seq.
def _heads_moved(moved: Sequence[tuple[Append, _Moved]]) -> dict[str, Any]:
    return {
        "logs": [append.log for append, _ in moved],
        "seqs": [outcome.seq for _, outcome in moved],
        "written": [outcome.written for _, outcome in moved],
        "written_seqs": [outcome.written_seq for _, outcome in moved],
        "agents": [None if append.kind == "score" else append.agent for append, _ in moved],
        "heads_calls": [None if append.kind == "score" else append.call for append, _ in moved],
        "heads_stamps": [None if append.kind == "score" else append.entries[0].ts for append, _ in moved],
    }


def _rows(entries: Sequence[Entry]) -> list[dict[str, Any]]:
    return [
        {
            "call": entry.call,
            "seq": entry.seq,
            "ts": entry.ts,
            "agent": entry.agent,
            "type": entry.type,
            "data": entry.data,
        }
        for entry in entries
        if not entry.ephemeral
    ]


# A caller that gave up has a cancelled future: its entries were written all the same.
def _answer(answer: asyncio.Future[Batch], outcome: Batch | Exception) -> None:
    if answer.done():
        return
    if isinstance(outcome, Exception):
        answer.set_exception(outcome)
        return
    answer.set_result(outcome)
