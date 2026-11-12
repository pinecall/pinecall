"""An org that spends strangely: today against its own trailing four weeks, said once a day."""

from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.actor import Scope
from runtime.alerts.service.alerts import Alerting
from runtime.kit.time import A_DAY_S
from runtime.wire.events import SpendUnusual

# Today is unusual once it costs this many times the org's usual day, the mean of its trailing
# four weeks; a usual day under a dollar is too small to judge, so a new org is never flagged.
UNUSUAL_MULTIPLE = 3.0
USUAL_AT_LEAST_USD = 1.0
TRAILING_DAYS = 28


# What the org's calls cost is read off the log's facts; the facts are calls', above alerts, so the
# function that reads them is handed in.
class SpendByDay(Protocol):
    """The org's spend from a day's start, and from `since` to it."""

    async def __call__(self, session: AsyncSession, org: str, day: float, since: float) -> tuple[float, float]:
        """The dollars since the day started, and those from `since` to its start."""
        ...


async def unusual_spend(session: AsyncSession, spend: SpendByDay, org: str, at: float) -> SpendUnusual | None:
    """Today's spend against the org's usual day, when it is over the line; None when usual."""
    day = _start_of_day(at)
    today, before = await spend(session, org, day, day - TRAILING_DAYS * A_DAY_S)
    usual = before / TRAILING_DAYS
    if usual < USUAL_AT_LEAST_USD or today < UNUSUAL_MULTIPLE * usual:
        return None
    named = datetime.fromtimestamp(day, UTC).date().isoformat()
    return SpendUnusual(
        org=org, day=named, today_usd=round(today, 6), usual_usd=round(usual, 6), multiple=round(today / usual, 2)
    )


# Said once a day on the agent's log: the alert's kind says so, and the alerts kept are where it is
# read (until 2026-11 the calls' log was scanned for it, with no lock). What was found is answered
# whether or not it was said, so the seal holds it up on /metrics for as long as it is unusual.
async def watch_spend(
    session: AsyncSession, alerting: Alerting, scope: Scope, agent: str, *, spend: SpendByDay, at: float
) -> SpendUnusual | None:
    """Say once a day, on the agent's log, that the org spends more today than it usually does; what was found."""
    found = await unusual_spend(session, spend, scope.org, at)
    if found is not None:
        await alerting.raise_alert(session, scope, agent, found)
    return found


def _start_of_day(at: float) -> float:
    """The UTC midnight the moment falls after, as a timestamp."""
    moment = datetime.fromtimestamp(at, UTC)
    return moment.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
