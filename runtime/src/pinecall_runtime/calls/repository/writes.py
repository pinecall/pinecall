"""The writer's statements: the heads of a group locked and moved, its rows written at once."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

# Outside the 32 bits of hashtext, which keys the runtime's other advisory locks.
FEED_ORDER_KEY = 0x9E3_C411_FEED

FEED_ORDER = text("select pg_advisory_xact_lock(:key)")

# Locked in the order of their names, so two writers never wait on each other's rows in a circle.
HEADS_LOCKED = text("""
select log, seq, sealed, written, written_seq from call_log_head
where log = any(:logs)
order by log
for update
""")

# A head at seq 0 for each log that begins in this group, rare beside the ones already there. One
# another writer made first is locked and read as it is: the update changes nothing of it.
HEADS_BEGUN = text("""
insert into call_log_head as head (log, agent, call)
select begun.log, begun.agent, begun.call
from unnest(cast(:logs as text[]), cast(:agents as text[]), cast(:calls as text[])) as begun(log, agent, call)
order by begun.log
on conflict (log) do update set log = head.log
returning log, seq, sealed, written, written_seq
""")

# The heads moved and the durable rows written in one statement: two tables, nothing between them
# to read. The rows travel as one JSON document, read apart by Postgres: six arrays of N were six
# parameters adapted a value at a time in Python, a fifth of the gateway's core at 100 calls.
WRITTEN = text("""
with moved as (
    update call_log_head as head
    set seq         = moved.seq,
        written     = moved.written,
        written_seq = moved.written_seq,
        agent       = coalesce(head.agent, moved.agent),
        call        = coalesce(head.call, moved.call),
        started_at  = coalesce(head.started_at, moved.started_at)
    from unnest(cast(:logs as text[]), cast(:seqs as bigint[]), cast(:written as bigint[]),
                cast(:written_seqs as bigint[]), cast(:agents as text[]), cast(:heads_calls as text[]),
                cast(:heads_stamps as float8[]))
         as moved(log, seq, written, written_seq, agent, call, started_at)
    where head.log = moved.log
)
insert into call_log (call, seq, ts, agent, type, ephemeral, data)
select kept.call, kept.seq, kept.ts, kept.agent, kept.type, false, kept.data
from jsonb_to_recordset(cast(:rows as jsonb))
     as kept(call text, seq bigint, ts float8, agent text, type text, data jsonb)
""").bindparams(bindparam("rows", type_=JSONB))

# The first-of-its-type requests whose log already holds an entry of that type: read under the
# heads' locks, so a second writer deciding the same end sees the first one's row.
HELD_TYPES = text("""
select distinct wanted.log
from unnest(cast(:logs as text[]), cast(:types as text[])) as wanted(log, type)
where exists (select 1 from call_log where log = wanted.log and type = wanted.type)
""")

# The answers of a tool call not needed: the log never asked that call id, or already holds its
# answer (the app's, or the timeout another gateway wrote). Read under the heads' locks, so of two
# gateways answering one call id the second sees the first's row.
UNANSWERABLE = text("""
select wanted.log
from unnest(cast(:logs as text[]), cast(:ids as text[])) as wanted(log, call_id)
where not exists (select 1 from call_log where log = wanted.log and type = 'tool.call'
                    and data ->> 'call_id' = wanted.call_id)
   or exists (select 1 from call_log where log = wanted.log and type = 'tool.result'
                and data ->> 'call_id' = wanted.call_id)
""")


@dataclass(frozen=True, slots=True)
class Head:
    """A head as the writer reads it under its lock."""

    log: str
    seq: int
    sealed: bool
    written: int
    written_seq: int | None


class WriteRepository:
    """The writer's statements on one transaction's session."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def take_feed_order(self) -> None:
        """Hold the fed lane's lock to the commit, so fed positions come in commit order."""
        await self.session.execute(FEED_ORDER, {"key": FEED_ORDER_KEY})

    async def lock_heads(self, logs: Sequence[str]) -> dict[str, Head]:
        """The heads of these logs, locked, by name."""
        rows = (await self.session.execute(HEADS_LOCKED, {"logs": list(logs)})).all()
        return {str(row.log): _head(row) for row in rows}

    async def begin_heads(
        self, logs: Sequence[str], agents: Sequence[str], calls: Sequence[str | None]
    ) -> dict[str, Head]:
        """A head for each log that begins now, locked; one made first is read as it is."""
        params = {"logs": list(logs), "agents": list(agents), "calls": list(calls)}
        rows = (await self.session.execute(HEADS_BEGUN, params)).all()
        return {str(row.log): _head(row) for row in rows}

    async def held_types(self, logs: Sequence[str], types: Sequence[str]) -> set[str]:
        """The logs among these that hold an entry of the type asked beside them."""
        if not logs:
            return set()
        rows = (await self.session.execute(HELD_TYPES, {"logs": list(logs), "types": list(types)})).all()
        return {str(row.log) for row in rows}

    async def unanswerable(self, logs: Sequence[str], ids: Sequence[str]) -> set[str]:
        """The logs among these that never asked the tool call id beside them, or answered it."""
        if not logs:
            return set()
        rows = (await self.session.execute(UNANSWERABLE, {"logs": list(logs), "ids": list(ids)})).all()
        return {str(row.log) for row in rows}

    async def write(self, heads_moved: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> None:
        """Move the heads and insert the durable rows in one statement."""
        await self.session.execute(WRITTEN, {**heads_moved, "rows": list(rows)})


def _head(row: Any) -> Head:
    return Head(
        log=str(row.log),
        seq=int(row.seq),
        sealed=bool(row.sealed),
        written=int(row.written),
        written_seq=None if row.written_seq is None else int(row.written_seq),
    )
