"""The log in Postgres as the engine reaches it: appends through the writer, reads in sessions."""

import time
from collections.abc import Callable, Sequence
from dataclasses import replace
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinecall_runtime.calls.facts import line_of
from pinecall_runtime.calls.models import log_name
from pinecall_runtime.calls.reducer import reduce
from pinecall_runtime.calls.repository.entries import EntryRepository, Positioned
from pinecall_runtime.calls.repository.facts import FactsRepository
from pinecall_runtime.calls.repository.heads import Claim, Claimant, HeadRepository
from pinecall_runtime.calls.repository.openings import PrivateRepository
from pinecall_runtime.calls.schemas import DEFAULT_LIMIT
from pinecall_runtime.calls.writer import FED_TYPES, Append, Batch, Unnumbered, Writer
from pinecall_runtime.exceptions import ValidationError
from pinecall_runtime.kit.text import JsonObject
from pinecall_runtime.wire.base import Entry

# The most entries a worker's batch may carry.
MOST_IN_A_BATCH = 256


class Store:
    """The log tables on sessions the store opens and closes itself, one per read or write."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession], *, clock: Callable[[], float] = time.time) -> None:
        """Keep the sessions and the clock entries are stamped with; appends go through a writer."""
        self.sessions = sessions
        # ts is the runtime's clock, when it saw the event, never the database's.
        self.clock = clock
        # This process, as the holder of the seals it leases.
        self.lease_id = uuid4().hex
        self.writer = Writer(sessions)

    # ── appends ──

    async def append(self, call: str | None, agent: str, kind: str, data: JsonObject, *, ephemeral: bool) -> Entry:
        """Write the entry with the next seq of its log, folding the call's facts with it."""
        entry = Unnumbered(type=kind, data=data, ephemeral=ephemeral, ts=self.clock())
        [written] = (await self.writer.write(Append("entry", log_name(call, agent), call, agent, [entry]))).entries
        return written

    # Two writers deciding the same end (a webhook delivered twice) write it once: the writer
    # looks under the head's lock, in the transaction that would write it.
    async def append_first(self, call: str, agent: str, kind: str, data: JsonObject) -> Entry | None:
        """Write a durable entry unless the call's log holds one of its type or is sealed."""
        entry = Unnumbered(type=kind, data=data, ephemeral=False, ts=self.clock())
        written = (await self.writer.write(Append("first", call, call, agent, [entry]))).entries
        return written[0] if written else None

    # Of two gateways answering one tool call (the app's answer, a timeout) the first stands.
    async def append_answer(self, call: str, agent: str, data: JsonObject) -> Entry | None:
        """Write a tool.result unless the log never asked its call id or answered it; None then."""
        entry = Unnumbered(type="tool.result", data=data, ephemeral=False, ts=self.clock())
        written = (await self.writer.write(Append("answer", call, call, agent, [entry]))).entries
        return written[0] if written else None

    # One writer, in order: `after` is how many entries the log took from it before this batch.
    async def append_many(self, call: str | None, agent: str, entries: Sequence[Unnumbered], *, after: int) -> Batch:
        """Write a worker's batch once under the next contiguous seqs, or answer a retry of it."""
        if not entries or len(entries) > MOST_IN_A_BATCH:
            raise ValidationError(f"a batch carries 1 to {MOST_IN_A_BATCH} entries, not {len(entries)}")
        stamped = [replace(item, ts=stamp) for item, stamp in zip(entries, _stamps(entries, self.clock()), strict=True)]
        return await self.writer.write(Append("batch", log_name(call, agent), call, agent, stamped, after=after))

    async def rescore(self, call: str, agent: str, data: JsonObject) -> Entry:
        """Write a call.score to a sealed log, the one entry a sealed log still takes."""
        score = Unnumbered(type="call.score", data=data, ephemeral=False, ts=self.clock())
        [written] = (await self.writer.write(Append("score", call, call, agent, [score]))).entries
        return written

    # ── reads ──

    async def since(self, log: str, *, after: int = 0, limit: int = DEFAULT_LIMIT) -> list[Entry]:
        """One page of the log's durable entries above the cursor, in seq order."""
        async with self.sessions() as session:
            return await EntryRepository(session).page(log, after=after, limit=limit)

    async def whole(self, log: str, *, after: int = 0) -> list[Entry]:
        """Every durable entry of the log above the cursor, oldest first."""
        async with self.sessions() as session:
            return await EntryRepository(session).whole(log, after=after)

    async def whole_with_private(self, log: str) -> tuple[list[Entry], dict[int, str]]:
        """Every durable entry of the log, and the sealed private values kept beside them."""
        async with self.sessions() as session:
            entries = await EntryRepository(session).whole(log)
            return entries, await PrivateRepository(session).of_log(log)

    async def latest_seq(self, log: str) -> int:
        """The last seq the log gave out, ephemerals counted; 0 for a log never written."""
        async with self.sessions() as session:
            return await HeadRepository(session).latest_seq(log)

    async def taken_count(self, log: str) -> int:
        """How many entries the log took from its writer's batches; 0 for none."""
        async with self.sessions() as session:
            return await HeadRepository(session).taken_count(log)

    async def is_sealed(self, log: str) -> bool:
        """Whether the log is sealed."""
        async with self.sessions() as session:
            return await HeadRepository(session).is_sealed(log)

    async def across(self, types: Sequence[str], *, after: int = 0, limit: int = DEFAULT_LIMIT) -> list[Positioned]:
        """One page of the fed entries of every log, by position, with their owners."""
        unfed = sorted(set(types) - FED_TYPES)
        if unfed:
            raise ValidationError(f"{', '.join(unfed)}: only the fed types are read across every log")
        async with self.sessions() as session:
            return await EntryRepository(session).across(types, after=after, limit=limit)

    async def owner(self, agent: str) -> str | None:
        """The org the agent's own log belongs to, or None while nobody claimed it."""
        async with self.sessions() as session:
            return await HeadRepository(session).owner(log_name(None, agent))

    async def claimant(self, call: str | None, agent: str) -> Claimant | None:
        """Whose the log is and in which env, or None while nobody claimed it."""
        async with self.sessions() as session:
            return await HeadRepository(session).claimant(log_name(call, agent))

    # ── the head's writes ──

    # The line is written with the seal: the list reads it from then on, and never folds this log.
    async def seal(self, call: str) -> None:
        """Seal the call's log and keep what a list shows of it; sealing twice changes nothing."""
        async with self.sessions.begin() as session:
            await HeadRepository(session).seal(call)
            entries = await EntryRepository(session).whole(call)
            await FactsRepository(session).set_line(call, line_of(reduce(entries)))

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

    async def claim(self, call: str | None, agent: str, org: str, claim: Claim | None = None) -> None:
        """Record the log's org, and for a call its scope and versions; the first claim stands."""
        async with self.sessions.begin() as session:
            await HeadRepository(session).claim(log_name(call, agent), agent, call, org, claim)

    async def keep_private(self, log: str, rows: Sequence[tuple[int, str]]) -> None:
        """Keep the sealed private values of these entries, by seq."""
        async with self.sessions.begin() as session:
            await PrivateRepository(session).keep(log, rows)

    async def private_of_entry(self, log: str, seq: int) -> str | None:
        """The sealed private value of one entry, or None."""
        async with self.sessions() as session:
            return await PrivateRepository(session).of_entry(log, seq)


# The worker's clock says when each thing happened; the gateway's bounds it, and a batch never
# steps back inside itself.
def _stamps(entries: Sequence[Unnumbered], now: float) -> list[float]:
    stamps: list[float] = []
    for item in entries:
        stamp = min(item.ts, now)
        stamps.append(stamp if not stamps else max(stamp, stamps[-1]))
    return stamps
