"""An org that spends strangely: today against its own trailing four weeks, said once a day."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.alerts.service.delivery import Logs, raise_alert
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.kit.handles import Handles
from pinecall_runtime.wire.events import SpendUnusual

# Today is unusual once it costs this many times the org's usual day, the mean of its trailing
# four weeks; a usual day under a dollar is too small to judge, so a new org is never flagged.
UNUSUAL_MULTIPLE = 3.0
USUAL_AT_LEAST_USD = 1.0
TRAILING_DAYS = 28
A_DAY_S = 86_400.0


@dataclass(frozen=True, slots=True)
class Unusual:
    """Today's spend against the usual day, and how many times it is."""

    day: str
    today_usd: float
    usual_usd: float
    multiple: float


class SpendLedger(Protocol):
    """What the org's calls cost, read off the log's facts; the facts are calls', above alerts, so handed in."""

    async def today_and_before(self, org: str, day: float, since: float) -> tuple[float, float]:
        """The org's spend from the day's start, and from `since` to it."""
        ...

    async def said_unusual_since(self, org: str, day: float) -> bool:
        """Whether spend.unusual was already written for the org since the day started."""
        ...


class SpendCounter(Protocol):
    """What /metrics shows of an org's spend; the gateway's counters are above alerts, so handed in."""

    def spending(self, org: str, multiple: float | None) -> None:
        """What the last seal found of the org's spend: unusual by this much, or None, usual."""
        ...


async def unusual_spend(ledger: SpendLedger, org: str, at: float) -> Unusual | None:
    """Today's spend against the org's usual day, when it is over the line; None when usual."""
    day = _start_of_day(at)
    today, before = await ledger.today_and_before(org, day, day - TRAILING_DAYS * A_DAY_S)
    usual = before / TRAILING_DAYS
    if usual < USUAL_AT_LEAST_USD or today < UNUSUAL_MULTIPLE * usual:
        return None
    named = datetime.fromtimestamp(day, UTC).date().isoformat()
    return Unusual(named, round(today, 6), round(usual, 6), round(today / usual, 2))


# Said once a day on the agent's log, and held up on /metrics for as long as it is unusual.
async def watch_spend(
    session: AsyncSession,
    handles: Handles,
    logs: Logs,
    counters: SpendCounter,
    scope: Scope,
    agent: str,
    *,
    ledger: SpendLedger,
    at: float,
) -> None:
    """Say once a day, on the agent's log, that the org spends more today than it usually does."""
    found = await unusual_spend(ledger, scope.org, at)
    counters.spending(scope.org, None if found is None else found.multiple)
    if found is None or await ledger.said_unusual_since(scope.org, _start_of_day(at)):
        return
    alert = SpendUnusual(
        org=scope.org, day=found.day, today_usd=found.today_usd, usual_usd=found.usual_usd, multiple=found.multiple
    )
    await raise_alert(session, handles, logs, scope, agent, alert)


def _start_of_day(at: float) -> float:
    """The UTC midnight the moment falls after, as a timestamp."""
    moment = datetime.fromtimestamp(at, UTC)
    return moment.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
