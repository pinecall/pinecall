"""The calls still open, as the reaper asks for them: the spoken ones gone quiet, the written ones a restart left."""

from dataclasses import dataclass

from sqlalchemy import TextClause, text

from runtime.calls.models import CallLogHead
from runtime.enums import Env
from runtime.kit.repository import Repository


@dataclass(frozen=True, slots=True)
class Unsealed:
    """A call still open, for the reaper: its start, its last move, its channel and its env."""

    call: str
    agent: str
    # None for a call that never reached call.started: an opening nobody joined.
    started_at: float | None
    last_at: float
    channel: str | None
    # None for a log no scope ever claimed.
    env: Env | None


# call_log is joined on log, its primary key's first column, never on call, which scans it.
# A call that never reached call.started may have no facts row, hence the left join.
# A head claimed at the open, whose first entry waits on the writer, moved last when it opened; a
# head with no entry, no start and no opening (a seal's lease) is never quiet. Under load this is
# the whole window: at 300 calls held the reaper sealed calls 36 ms after they opened (2026-10-01).
UNSEALED_SPOKEN = text("""
select head.log as call, head.agent,
       head.started_at,
       coalesce(max(entry.ts), head.started_at, extract(epoch from opening.opened_at)) as last_at,
       null as channel, head.env
from call_log_head head
left join call_facts f on f.call = head.log
left join call_openings opening on opening.call = head.log
left join call_log entry on entry.log = head.log
where head.call is not null and not head.sealed
  and (coalesce(f.spoken, false)
       or not exists (select 1 from call_log began
                       where began.log = head.log and began.type = 'call.started'))
group by head.log, head.agent, head.started_at, head.env, opening.opened_at
having coalesce(max(entry.ts), head.started_at, extract(epoch from opening.opened_at)) < :quiet_since
order by last_at
limit :limit
""")

UNSEALED_WRITTEN = text("""
select head.log as call, head.agent,
       head.started_at,
       coalesce(max(entry.ts), head.started_at, 0) as last_at, f.channel, head.env
from call_log_head head
join call_facts f on f.call = head.log
left join call_log entry on entry.log = head.log
where head.call is not null and not head.sealed and not coalesce(f.spoken, false)
  and exists (select 1 from call_log began
               where began.log = head.log and began.type = 'call.started')
group by head.log, head.agent, head.started_at, head.env, f.channel
having coalesce(max(entry.ts), head.started_at, 0) < :quiet_since
order by last_at
limit :limit
""")


class UnsealedRepository(Repository[CallLogHead]):
    """The heads of the calls nobody sealed, read across every org by the reaper."""

    model = CallLogHead

    # Across every org: the reaper's question. A call that never reached call.started is reaped
    # whatever its channel.
    async def list_spoken(self, quiet_since: float, *, limit: int) -> list[Unsealed]:
        """The spoken or never-started calls still open and quiet since then, oldest first."""
        return await self._list(UNSEALED_SPOKEN, quiet_since, limit)

    # A written call idles out where it runs; this finds the ones a restart left open.
    async def list_written(self, quiet_since: float, *, limit: int) -> list[Unsealed]:
        """The written calls still open and quiet since then, with their channel."""
        return await self._list(UNSEALED_WRITTEN, quiet_since, limit)

    async def _list(self, statement: TextClause, quiet_since: float, limit: int) -> list[Unsealed]:
        rows = (await self.session.execute(statement, {"quiet_since": quiet_since, "limit": limit})).all()
        return [
            Unsealed(
                call=str(row.call),
                agent=str(row.agent or ""),
                started_at=None if row.started_at is None else float(row.started_at),
                last_at=float(row.last_at),
                channel=row.channel,
                env=None if row.env is None else Env(row.env),
            )
            for row in rows
        ]
