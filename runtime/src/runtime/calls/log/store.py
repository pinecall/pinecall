"""The log in Postgres as the engine reaches it: appends through the writer, the seal, reads on sessions of its own."""

from collections.abc import Callable, Sequence
from dataclasses import replace
from typing import overload
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.calls.context import log_name
from runtime.calls.folds.facts import line_of
from runtime.calls.folds.state import reduce
from runtime.calls.log.writer import FED_TYPES, Append, Batch, Guarded, Kind, Sure, Unnumbered, Writer
from runtime.calls.repository.entries import A_PAGE, EntryRepository, Positioned
from runtime.calls.repository.facts import FactsRepository
from runtime.calls.repository.heads import Claimant, HeadRepository
from runtime.calls.repository.private import PrivateRepository
from runtime.exceptions import ValidationError
from runtime.kit.text import JsonObject
from runtime.kit.time import epoch
from runtime.scoping import box_wide
from runtime.wire.base import Entry

# The most entries a worker's batch may carry.
MOST_IN_A_BATCH = 256

# The process's clock, as seconds since the epoch: what every entry, marker and piece of news is
# stamped with. A test hands in its own.
type Clock = Callable[[], float]


# A log, its relay and its feeds outlive every request, so what they read and write of the tables
# is on a session opened here, one per operation. A use case that holds a request's session reads
# the same rows through the repositories with that session: asking the store too would hold a
# second connection of a pool that does not grow.
class Store:
    """The log tables on sessions the store opens and closes itself, one per read or write."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession], writer: Writer, *, clock: Clock = epoch) -> None:
        """Keep the sessions, the process's writer, and the clock entries are stamped with."""
        self.sessions = sessions
        # The process builds the writer, with a pool of its own when it has one to give (the gateway
        # does, one connection per lane): an append then never waits on a request for a connection.
        self.writer = writer
        # ts is the runtime's clock, when it saw the event, never the database's.
        self.clock = clock
        # This process, as the holder of the seals it leases.
        self.lease_id = uuid4().hex

    # ── appends ──

    @overload
    async def write(
        self, how: Sure, call: str | None, agent: str, kind: str, data: JsonObject, *, ephemeral: bool = False
    ) -> Entry: ...

    @overload
    async def write(
        self, how: Guarded, call: str | None, agent: str, kind: str, data: JsonObject, *, ephemeral: bool = False
    ) -> Entry | None: ...

    # The writer's `Kind` says which of the ways it is. An entry of the gateway's own takes the next
    # seq of its log, the call's facts folded with it; a verdict is the one entry a sealed log still
    # takes. A first-of-its-type and an answer are looked at under the head's lock, in the
    # transaction that would write them: of two writers deciding the same end (a webhook delivered
    # twice), or two gateways answering one tool call (the app's answer, a timeout), the first stands.
    async def write(
        self, how: Sure | Guarded, call: str | None, agent: str, kind: str, data: JsonObject, *, ephemeral: bool = False
    ) -> Entry | None:
        """Write one entry in the way named; None when the log did not need it (a first, an answer)."""
        entry = Unnumbered(type=kind, data=data, ephemeral=ephemeral, ts=self.clock())
        written = (await self._write(how, call, agent, [entry])).entries
        return written[0] if written else None

    # One writer, in order: `after` is how many entries the log took from it before this batch.
    async def write_many(self, call: str | None, agent: str, entries: Sequence[Unnumbered], *, after: int) -> Batch:
        """Write a worker's batch once under the next contiguous seqs, or answer a retry of it."""
        if not entries or len(entries) > MOST_IN_A_BATCH:
            raise ValidationError(f"a batch carries 1 to {MOST_IN_A_BATCH} entries, not {len(entries)}")
        stamped = [replace(item, ts=stamp) for item, stamp in zip(entries, _stamps(entries, self.clock()), strict=True)]
        return await self._write("batch", call, agent, stamped, after=after)

    async def _write(
        self, how: Kind, call: str | None, agent: str, entries: Sequence[Unnumbered], *, after: int = 0
    ) -> Batch:
        return await self.writer.write(Append(how, log_name(call, agent), call, agent, entries, after=after))

    # ── reads ──

    async def page_of(self, log: str, *, after: int = 0, limit: int = A_PAGE) -> list[Entry]:
        """One page of the log's durable entries above the cursor, in seq order."""
        async with self.sessions() as session:
            return await EntryRepository(session).page_of(log, after=after, limit=limit)

    async def whole_of(self, log: str, *, after: int = 0) -> list[Entry]:
        """Every durable entry of the log above the cursor, oldest first."""
        async with self.sessions() as session:
            return await EntryRepository(session).whole_of(log, after=after)

    async def seq_of(self, log: str) -> int:
        """The last seq the log gave out, ephemerals counted; 0 for a log never written."""
        async with self.sessions() as session:
            return await HeadRepository(session).seq_of(log)

    async def is_sealed(self, log: str) -> bool:
        """Whether the log is sealed."""
        async with self.sessions() as session:
            return await HeadRepository(session).is_sealed(log)

    # A feed is read for as long as its reader stays, a page at a time between waits: never on a
    # request's session, which is handed back when the endpoint returns.
    async def list_across(self, types: Sequence[str], *, after: int = 0, limit: int = A_PAGE) -> list[Positioned]:
        """One page of the fed entries of every log, by position, with their owners."""
        unfed = sorted(set(types) - FED_TYPES)
        if unfed:
            raise ValidationError(f"{', '.join(unfed)}: only the fed types are read across every log")
        async with self.sessions() as session:
            return await EntryRepository(session).list_across(types, after=after, limit=limit)

    # Whose a log is decides who may read it: asked box-wide, so another org's log reads as that
    # org's (a 404 to the asker) and never as nobody's (postgres.py, migration 0096).
    async def owner(self, agent: str) -> str | None:
        """The org the agent's own log belongs to, or None while nobody claimed it."""
        async with self.sessions() as session:
            with box_wide():
                return await HeadRepository(session).owner_of(log_name(None, agent))

    async def claimant_of(self, call: str | None, agent: str) -> Claimant | None:
        """Whose the log is and in which env, or None while nobody claimed it."""
        async with self.sessions() as session:
            with box_wide():
                return await HeadRepository(session).claimant_of(log_name(call, agent))

    # ── the seal ──

    # The line is written with the seal: the list reads it from then on, and never folds this log.
    async def seal(self, call: str) -> None:
        """Seal the call's log and keep what a list shows of it; sealing twice changes nothing."""
        async with self.sessions.begin() as session:
            await HeadRepository(session).seal(call)
            entries = await EntryRepository(session).whole_of(call)
            await FactsRepository(session).keep(call, line=line_of(reduce(entries)))

    async def lease_seal(self, call: str, seconds: float) -> bool:
        """Take the right to seal the call for so long; False when another holds it, or it ended."""
        async with self.sessions.begin() as session:
            return await HeadRepository(session).lease_seal(call, seconds, self.lease_id)

    async def renew_seal(self, call: str, seconds: float) -> None:
        """Hold the right to seal the call for so long again, while sealing it."""
        async with self.sessions.begin() as session:
            await HeadRepository(session).renew_seal(call, seconds, self.lease_id)

    async def release_seal(self, call: str) -> None:
        """Give the right to seal back, after a seal that broke: the next request takes it."""
        async with self.sessions.begin() as session:
            await HeadRepository(session).release_seal(call, self.lease_id)

    # ── what a log sealed aside ──

    async def keep_private(self, log: str, rows: Sequence[tuple[int, str]]) -> None:
        """Keep the sealed private values of these entries, by seq."""
        async with self.sessions.begin() as session:
            await PrivateRepository(session).keep(log, rows)

    async def whole_with_private(self, log: str) -> tuple[list[Entry], dict[int, str]]:
        """Every durable entry of the log, and the sealed private values kept beside them."""
        async with self.sessions() as session:
            entries = await EntryRepository(session).whole_of(log)
            return entries, await PrivateRepository(session).list_of_log(log)

    async def list_private_tool_calls(self, log: str, after: int) -> list[tuple[Entry, str]]:
        """The tool.call entries above `after` that kept private values, with them sealed."""
        async with self.sessions() as session:
            return await PrivateRepository(session).list_of_tool_calls(log, after)

    async def find_private(self, log: str, seq: int) -> str | None:
        """The sealed private value of one entry, or None."""
        async with self.sessions() as session:
            return await PrivateRepository(session).find_of_entry(log, seq)


# The worker's clock says when each thing happened; the gateway's bounds it, and a batch never
# steps back inside itself.
def _stamps(entries: Sequence[Unnumbered], now: float) -> list[float]:
    stamps: list[float] = []
    for item in entries:
        stamp = min(item.ts, now)
        stamps.append(stamp if not stamps else max(stamp, stamps[-1]))
    return stamps
