"""The WAL archive: what Postgres says of the archiver and of the spool, judged for the doctor."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.platform.repository import ArchiveRepository

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
    archiving = ArchiveRepository(session)
    state = await archiving.archiver()
    if state is None or state[0] == "off":
        return Archive("off", None, None, None, 0, None)
    mode, archived, failed, wal = state
    waiting, oldest = (0, None) if not spool else await archiving.spooled(spool)
    return Archive(mode, archived, failed, wal, waiting, oldest)


def archive_finding(archive: Archive, now: datetime) -> tuple[str | None, str]:
    """The trouble with the archive, or None, and the state an ok line says."""
    if archive.mode == "off":
        return None, OFF
    failed, archived = archive.last_failed, archive.last_archived
    if failed is not None and (archived is None or failed > archived):
        return NOT_SPOOLED.format(wal=archive.failed_wal, at=failed), ""
    oldest = archive.oldest
    if oldest is not None and (now - oldest).total_seconds() > SHIPPED_WITHIN_S:
        return NOT_SHIPPED.format(waiting=archive.waiting, at=oldest), ""
    ago = "never" if archived is None else f"{int((now - archived).total_seconds())} s ago"
    return None, ON.format(waiting=archive.waiting, ago=ago)
