"""The night: the calls past their org's days erased, and every domain forgetting what it keeps for a while."""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.actor import Scope
from runtime.alerts import service as alerts
from runtime.calls import service as calls
from runtime.compliance import service as compliance
from runtime.postgres import BoxSession, without_timeouts
from runtime.retention.repository.due import Due, DueRepository
from runtime.retention.service.erasure import Erasing, erase_call
from runtime.whatsapp import service as whatsapp

# Who asked, in the erasure trail, for what the calendar erased.
RETENTION = "retention"
# One night's work at most; what is left over is the next night's.
A_RUN_ERASES = 5000


@dataclass(frozen=True, slots=True)
class Nightly:
    """What one night did: the calls erased, the records, dials, message ids and alerts forgotten, the days."""

    erased: list[str]
    records: int
    dials: int
    seen: int
    alerts: int
    days: calls.DaysKept


async def list_due(session: AsyncSession, now: float, *, limit: int = A_RUN_ERASES) -> list[Due]:
    """The sealed calls whose org keeps fewer days than they have, oldest first."""
    async with without_timeouts(session):
        return await DueRepository(session).list_due(now, limit=limit)


# One transaction per call: a night that stops halfway has erased whole calls, each with its trail.
async def erase_due(
    sessions: async_sessionmaker[AsyncSession], erasing: Erasing, now: float, *, limit: int = A_RUN_ERASES
) -> list[str]:
    """Erase every call past its org's days, one erasure each; the calls erased."""
    async with sessions.begin() as session:
        due = await list_due(session, now, limit=limit)
    for found in due:
        async with sessions.begin() as session:
            await erase_call(session, erasing, Scope(found.org, found.env), found.call, by=RETENTION)
    return [found.call for found in due]


# Each domain forgets what is its own, by its own verb and on its own term: a phone call's record and a
# dial two years on, a WhatsApp message id once Meta no longer delivers it again, an alert past its days.
async def run_nightly(sessions: async_sessionmaker[AsyncSession], erasing: Erasing, now: float) -> Nightly:
    """The night's run: the calls due, the old records, dials, message ids and alerts, and the log's days."""
    erased = await erase_due(sessions, erasing, now)
    moment = datetime.fromtimestamp(now, UTC)
    async with sessions.begin() as session, without_timeouts(session):
        records = await calls.forget_records(session, now)
        dials = await compliance.forget_dials(session, moment)
        seen = await whatsapp.forget_seen_before(session, moment)
        old_alerts = await alerts.forget_alerts(BoxSession(session), moment)
        days = await calls.keep_days(session, now)
    return Nightly(erased=erased, records=records, dials=dials, seen=seen, alerts=old_alerts, days=days)
