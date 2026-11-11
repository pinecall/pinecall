"""What Postgres says of itself: how far its standbys lag, its archiver, the spool its WAL leaves from."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# A lag never replayed yet (a replica caught up and idle) reads as zero.
REPLICAS = text("""
select application_name as replica, extract(epoch from coalesce(replay_lag, interval '0')) as lag
from pg_stat_replication
""")
ARCHIVER = text("""
select current_setting('archive_mode') as mode, last_archived_time, last_failed_time, last_failed_wal
from pg_stat_archiver
""")
# Read through Postgres, which has the spool mounted: the doctor's own user reads no WAL.
SPOOLED = text("""
select count(*) as waiting, min(file.modification) as oldest
from pg_ls_dir(:spool, true, false) as name,
     lateral pg_stat_file(:spool || '/' || name, true) as file
where not file.isdir and name not like '%.part'
""")


@dataclass(frozen=True, slots=True)
class ReplicaLag:
    """One standby by name, and how far behind it is in replaying the primary's WAL, in seconds."""

    replica: str
    lag_s: float


@dataclass(frozen=True, slots=True)
class Archiver:
    """The archive mode, when a segment last shipped, when one last failed, and which."""

    mode: str
    last_archived: datetime | None
    last_failed: datetime | None
    failed_wal: str | None


@dataclass(frozen=True, slots=True)
class Spool:
    """How many segments wait in the spool, and the oldest's modification time."""

    waiting: int
    oldest: datetime | None


class DatabaseRepository:
    """Postgres's own views, read on a session."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_replica_lags(self) -> list[ReplicaLag]:
        """Each standby and its replay lag."""
        rows = (await self.session.execute(REPLICAS)).all()
        return [ReplicaLag(str(replica), float(lag)) for replica, lag in rows]

    async def find_archiver(self) -> Archiver | None:
        """The archiver's state, or None where Postgres reports none."""
        row = (await self.session.execute(ARCHIVER)).first()
        if row is None:
            return None
        mode, archived, failed, wal = row
        return Archiver(str(mode), archived, failed, None if wal is None else str(wal))

    async def get_spool(self, spool: str) -> Spool:
        """What waits in the spool at that path."""
        waiting, oldest = (await self.session.execute(SPOOLED, {"spool": spool})).one()
        return Spool(int(waiting), oldest)
