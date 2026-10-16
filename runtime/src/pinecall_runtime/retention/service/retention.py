"""Retention: calls past their org's days (the policy), call records and dials past two years."""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinecall_runtime.calls import service as calls
from pinecall_runtime.channels import service as channels
from pinecall_runtime.kit.auth import THE_ORGS_OWN, Scope
from pinecall_runtime.postgres import unbounded
from pinecall_runtime.retention.repository import DueRepository
from pinecall_runtime.retention.service.erasure import erase_call

# An erased phone call's record and every dial are kept for a carrier's traceback this long.
RECORDS_KEPT_S = 730 * 86_400
# Who asked, in the erasure trail, for what the calendar erased.
RETENTION = "retention"
# One night's work at most; what is left over is the next night's.
A_RUN_ERASES = 5000


@dataclass(frozen=True, slots=True)
class Due:
    """A sealed call past its org's days: whose it is, and which."""

    scope: Scope
    call: str


@dataclass(frozen=True, slots=True)
class Nightly:
    """What one night did: the calls erased, the records, dials and message ids forgotten, the days."""

    erased: list[str]
    records: int
    dials: int
    seen: int
    days: calls.DaysKept


async def due_calls(session: AsyncSession, now: float, *, limit: int = A_RUN_ERASES) -> list[Due]:
    """The sealed calls whose org keeps fewer days than they have, oldest first."""
    async with unbounded(session):
        rows = await DueRepository(session).due(now, limit=limit)
    return [Due(Scope(row.org, row.env, row.holder or THE_ORGS_OWN), row.call) for row in rows]


# One transaction per call: a night that stops halfway has erased whole calls, each with its trail.
async def purge(
    sessions: async_sessionmaker[AsyncSession], recordings: calls.Recordings, now: float, *, limit: int = A_RUN_ERASES
) -> list[str]:
    """Erase every call past its org's days, one erasure each; the calls erased."""
    async with sessions.begin() as session:
        due = await due_calls(session, now, limit=limit)
    for found in due:
        async with sessions.begin() as session:
            await erase_call(session, recordings, found.scope, found.call, by=RETENTION)
    return [found.call for found in due]


async def forget_records(session: AsyncSession, now: float) -> int:
    """Forget the records of erased calls more than two years old; how many."""
    async with unbounded(session):
        return await DueRepository(session).forget_records(now - RECORDS_KEPT_S)


async def forget_dials(session: AsyncSession, now: float) -> int:
    """Forget the dials placed or refused more than two years ago; how many."""
    async with unbounded(session):
        return await DueRepository(session).forget_dials(now - RECORDS_KEPT_S)


async def run_nightly(sessions: async_sessionmaker[AsyncSession], recordings: calls.Recordings, now: float) -> Nightly:
    """The night's run: the calls due, the old records, dials and message ids, and the log's days."""
    erased = await purge(sessions, recordings, now)
    async with sessions.begin() as session:
        records = await forget_records(session, now)
        dials = await forget_dials(session, now)
        seen = await channels.forget_seen_before(session, datetime.fromtimestamp(now, UTC))
        days = await calls.keep_days(session, now)
    return Nightly(erased=erased, records=records, dials=dials, seen=seen, days=days)
