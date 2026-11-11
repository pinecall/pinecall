"""The database's health: its WAL archive judged for the doctor, and how far its standbys lag."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.platform.repository.database import DatabaseRepository, ReplicaLag

# The timer ships every 10 s: five minutes of segments waiting is a bucket that does not answer.
SHIPPED_WITHIN_S = 300

OFF = "off: no restore to a minute; the postgres chart's backups section turns the archiver on"
NOT_SPOOLED = (
    "segment {wal} could not be spooled at {at:%Y-%m-%d %H:%M:%S}Z: Postgres keeps it in pg_wal "
    "and retries, and pg_wal grows until it can"
)
NOT_SHIPPED = (
    "{waiting} segments waiting since {at:%Y-%m-%d %H:%M:%S}Z: the bucket has not taken them "
    "(the postgres pod's logs say why); they stay on this disk until it does"
)
ON = "on, {waiting} waiting to ship, the last spooled {ago}"


@dataclass(frozen=True, slots=True)
class Archive:
    """What Postgres says of its archiving, and what waits in the spool to leave the box."""

    mode: str
    last_archived: datetime | None
    last_failed: datetime | None
    failed_wal: str | None
    waiting: int
    oldest: datetime | None


# A box ships its WAL through a spool (PINECALL_WAL_SPOOL), read here through Postgres; a
# cluster's operator archives with none, and its spool is unset: the archiver's state alone.
async def archive_of(session: AsyncSession, spool: str | None) -> Archive:
    """The archiver's state and, when it is on and a spool is named, the spool's backlog."""
    database = DatabaseRepository(session)
    archiver = await database.find_archiver()
    if archiver is None or archiver.mode == "off":
        return Archive("off", None, None, None, 0, None)
    waiting, oldest = 0, None
    if spool:
        kept = await database.get_spool(spool)
        waiting, oldest = kept.waiting, kept.oldest
    return Archive(archiver.mode, archiver.last_archived, archiver.last_failed, archiver.failed_wal, waiting, oldest)


@dataclass(frozen=True, slots=True)
class ArchiveFinding:
    """What the doctor says of the archive: its trouble, if any, and otherwise the state an ok line says."""

    trouble: str | None
    state: str


def judge_archive(archive: Archive, now: datetime) -> ArchiveFinding:
    """The trouble with the archive, or its state when there is none."""
    if archive.mode == "off":
        return ArchiveFinding(None, OFF)
    failed, archived = archive.last_failed, archive.last_archived
    if failed is not None and (archived is None or failed > archived):
        return ArchiveFinding(NOT_SPOOLED.format(wal=archive.failed_wal, at=failed), "")
    oldest = archive.oldest
    if oldest is not None and (now - oldest).total_seconds() > SHIPPED_WITHIN_S:
        return ArchiveFinding(NOT_SHIPPED.format(waiting=archive.waiting, at=oldest), "")
    ago = "never" if archived is None else f"{int((now - archived).total_seconds())} s ago"
    return ArchiveFinding(None, ON.format(waiting=archive.waiting, ago=ago))


async def list_replica_lags(session: AsyncSession) -> list[ReplicaLag]:
    """How far behind each standby of the database is, by its name."""
    return await DatabaseRepository(session).list_replica_lags()
