"""The reads a rebuild and the doctor make of the log: pages of calls, a head's rows, a sample."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Row, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.calls.models import CallLog, CallLogHead
from pinecall_runtime.calls.repository.entries import COLUMNS, entry_of
from pinecall_runtime.wire.base import Entry

# The append's own lock: an append waits for the refold, and the refold reads what it wrote.
HEAD_LOCKED = text("select log from call_log_head where log = :call for update")

# Snapshot reads: an append writes its entries and its facts in one transaction, so one snapshot
# sees both or neither.
SNAPSHOT = text("set transaction isolation level repeatable read, read only")

# The heads doctor examines: the newest calls by the log's own order (the index of an entry's
# type and position finds the last call.started without reading the rest), and as many from a
# random point of the heads' key, round to the start. Each is one probe of the log's primary key:
# a head is never behind a row it numbered. Every head would be a probe per call on the box.
HEADS_BEHIND = text("""
with newest as (
    select log from call_log where type = 'call.started' order by position desc limit :limit
), sampled as (
    (select log from call_log_head where log >= :start order by log limit :limit)
    union all
    (select log from call_log_head where log < :start order by log limit :limit)
    limit :limit
), examined as (select log from newest union select log from sampled)
select examined.log,
       head.seq < (select max(entry.seq) from call_log entry where entry.log = examined.log) as behind
from examined join call_log_head head on head.log = examined.log
order by examined.log
""")

# From a random point of the call ids, round to the start: a sample the primary key finds.
SAMPLE = text("""
(select log from call_log_head where call is not null and sealed and log >= :start order by log limit :limit)
union all
(select log from call_log_head where call is not null and sealed and log < :start order by log limit :limit)
limit :limit
""")


@dataclass(frozen=True)
class Refolding:
    """Which calls a rebuild refolds: one, an org's, those started since; every call when none."""

    call: str | None = None
    org: str | None = None
    since: float | None = None


class RefoldRepository:
    """What a rebuild and the doctor read of the log."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def calls_after(self, refolding: Refolding, after: str, limit: int) -> list[str]:
        """A page of the calls the rebuild names, past the cursor."""
        statement = select(CallLogHead.log).where(CallLogHead.call.is_not(None), CallLogHead.log > after)
        if refolding.call is not None:
            statement = statement.where(CallLogHead.log == refolding.call)
        if refolding.org is not None:
            statement = statement.where(CallLogHead.org == refolding.org)
        if refolding.since is not None:
            statement = statement.where(CallLogHead.started_at >= refolding.since)
        rows = await self.session.execute(statement.order_by(CallLogHead.log).limit(limit))
        return [str(log) for log in rows.scalars()]

    async def lock_head(self, call: str) -> None:
        """Hold the call's head for this transaction, as an append would."""
        await self.session.execute(HEAD_LOCKED, {"call": call})

    async def snapshot(self) -> None:
        """Read this transaction off one snapshot."""
        await self.session.execute(SNAPSHOT)

    async def entries_of(self, call: str) -> list[Entry]:
        """Every durable entry of the call, in seq order."""
        statement = (
            select(*(getattr(CallLog, name) for name in COLUMNS)).where(CallLog.log == call).order_by(CallLog.seq)
        )
        return [entry_of(row) for row in (await self.session.execute(statement)).all()]

    async def heads_behind(self, start: str, limit: int) -> Sequence[Row[Any]]:
        """The heads examined, each with whether its rows are past its seq."""
        return (await self.session.execute(HEADS_BEHIND, {"start": start, "limit": limit})).all()

    async def sample(self, start: str, limit: int) -> list[str]:
        """A sample of sealed calls from a random point of their ids."""
        rows = await self.session.execute(SAMPLE, {"start": start, "limit": limit})
        return [str(row.log) for row in rows.all()]
