"""The reads a rebuild and the doctor make of the log: pages of calls, a head locked, the heads behind, a sample."""

from dataclasses import dataclass

from sqlalchemy import select, text

from runtime.calls.models import CallLogHead
from runtime.kit.repository import Repository

# The append's own lock: an append waits for the refold, and the refold reads what it wrote.
HEAD_LOCKED = text("select log from call_log_head where log = :call for update")

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


@dataclass(frozen=True, slots=True)
class Refolding:
    """Which calls a rebuild refolds: one, an org's, those started since; every call when none."""

    call: str | None = None
    org: str | None = None
    since: float | None = None


@dataclass(frozen=True, slots=True)
class HeadExamined:
    """A head the doctor looked at, and whether its log holds rows past the seq it says."""

    log: str
    behind: bool


class RebuildRepository(Repository[CallLogHead]):
    """What a rebuild and the doctor read of the log's heads."""

    model = CallLogHead

    async def list_calls_after(self, refolding: Refolding, after: str, limit: int) -> list[str]:
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

    async def list_heads_behind(self, start: str, limit: int) -> list[HeadExamined]:
        """The heads examined, each with whether its rows are past its seq."""
        rows = (await self.session.execute(HEADS_BEHIND, {"start": start, "limit": limit})).all()
        return [HeadExamined(str(row.log), bool(row.behind)) for row in rows]

    async def list_sample(self, start: str, limit: int) -> list[str]:
        """A sample of sealed calls from a random point of their ids."""
        rows = await self.session.execute(SAMPLE, {"start": start, "limit": limit})
        return [str(row.log) for row in rows.all()]
