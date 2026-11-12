"""The newborn orgs looked at once: one a day old with no call that went well is pointed at, to the operators."""

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.accounts import service as accounts
from runtime.accounts.models import Org
from runtime.actor import Scope
from runtime.alerts.repository import AlertRepository
from runtime.alerts.service import kinds
from runtime.alerts.service.alerts import Alerting, claim_alert
from runtime.alerts.service.mail import mail_quiet_digest
from runtime.enums import Env
from runtime.kit.time import now
from runtime.scoping import box_wide
from runtime.wire.feed import OrgQuiet

# An org is looked at once it is this old, and no longer once it is this old.
QUIET_AFTER = timedelta(hours=24)
NEWBORN_FOR = timedelta(days=7)


# The calls of an org are calls', above alerts: the function that lists the ended ones is handed in.
class EndedCalls(Protocol):
    """The org's calls that ended, in either env."""

    async def __call__(self, session: AsyncSession, org: str) -> Sequence[str]:
        """The ids of the calls."""
        ...


async def watch_newborns(
    sessions: async_sessionmaker[AsyncSession],
    alerting: Alerting,
    ended_calls: EndedCalls,
    *,
    at: datetime | None = None,
) -> list[str]:
    """Point at every newborn org a day old with no call that went well, once each, in one mail; the orgs pointed at."""
    at = at or now()
    async with sessions() as session:
        newborns = await accounts.list_newborns(session, at - NEWBORN_FOR, at - QUIET_AFTER)
    quiets: list[OrgQuiet] = []
    # One transaction per org: the sweep never holds a connection across the orgs.
    for org in newborns:
        async with sessions.begin() as session:
            quiet = await _point_at(session, alerting, ended_calls, org)
            if quiet is not None:
                quiets.append(quiet)
    if quiets:
        async with sessions.begin() as session:
            await mail_quiet_digest(session, alerting.outbox, alerting.address, quiets)
    return [quiet.org for quiet in quiets]


# Two gateways sweeping the same hour would both find the org quiet and both say so: the first to
# claim it says it, the second finds the alert kept once the first commits. The claim comes before
# the org's calls are read, so an org pointed at once costs a sweep one lookup for the week it is new.
async def _point_at(session: AsyncSession, alerting: Alerting, ended_calls: EndedCalls, org: Org) -> OrgQuiet | None:
    scope = Scope(org.id, Env.sandbox)
    with box_wide():
        if not await claim_alert(session, scope, kinds.ORG_QUIET, org.id):
            return None
        ended = await ended_calls(session, org.id)
        failed = await AlertRepository(session).list_failed_calls(org.id)
        if set(ended) - failed:
            return None
        quiet = OrgQuiet(
            org=org.id,
            name=org.name,
            created_at=org.created_at.timestamp(),
            calls=len(ended),
            failed=len([call for call in ended if call in failed]),
        )
        await alerting.raise_alert(session, scope, None, quiet)
    return quiet
