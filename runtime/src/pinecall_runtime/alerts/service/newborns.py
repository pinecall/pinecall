"""The newborn orgs looked at once: one a day old with no call that went well is pointed at, to the operators."""

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinecall_runtime.accounts.models import Org
from pinecall_runtime.accounts.service import orgs
from pinecall_runtime.alerts.repository import AlertRepository
from pinecall_runtime.alerts.service.delivery import Alerting, org_quiet
from pinecall_runtime.alerts.service.telling import mail_quiet_digest
from pinecall_runtime.enums import Env
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.kit.loops import survived
from pinecall_runtime.kit.time import now
from pinecall_runtime.postgres import box_wide
from pinecall_runtime.wire.feed import OrgQuiet

logger = logging.getLogger(__name__)

KIND = "org.quiet"
# An org is looked at once it is this old, and no longer once it is this old.
QUIET_AFTER = timedelta(hours=24)
NEWBORN_FOR = timedelta(days=7)
# How often a gateway sweeps; the lock on the org keeps two gateways from saying it twice.
SWEPT_EVERY_S = 3600.0


class CallLedger(Protocol):
    """The calls of an org as the calls domain keeps them, handed in: alerts stand below calls."""

    async def ended_of_org(self, org: str) -> list[str]:
        """The org's calls that ended, in either env."""
        ...


async def watch_newborns(
    sessions: async_sessionmaker[AsyncSession],
    alerting: Alerting,
    ledger_of: Callable[[AsyncSession], CallLedger],
    *,
    at: datetime | None = None,
) -> list[str]:
    """Point at every newborn org a day old with no call that went well, once each, in one mail; the orgs pointed at."""
    at = at or now()
    async with sessions() as session:
        newborns = await orgs.list_newborns(session, at - NEWBORN_FOR, at - QUIET_AFTER)
    quiets: list[OrgQuiet] = []
    # One transaction per org: the sweep never holds a connection across the orgs, nor across the
    # webhooks an alert waits on.
    for org in newborns:
        async with sessions.begin() as session:
            quiet = await _point_at(session, alerting, ledger_of(session), org)
            if quiet is not None:
                quiets.append(quiet)
    if quiets:
        async with sessions() as session:
            await mail_quiet_digest(
                session, alerting.outbox, alerting.handles.settings.address, [q.dump() for q in quiets]
            )
    return [quiet.org for quiet in quiets]


async def _point_at(session: AsyncSession, alerting: Alerting, ledger: CallLedger, org: Org) -> OrgQuiet | None:
    with box_wide():
        alerts = AlertRepository(session)
        if await alerts.kept_since(org.id, Env.sandbox, KIND, org.id, org.created_at):
            return None
        if not await alerts.claim_subject(KIND, org.id):
            return None
        ended = await ledger.ended_of_org(org.id)
        failed = await alerts.calls_failed_of(org.id)
    if set(ended) - failed:
        return None
    quiet = OrgQuiet(
        org=org.id,
        name=org.name,
        created_at=org.created_at.timestamp(),
        calls=len(ended),
        failed=len([call for call in ended if call in failed]),
    )
    await org_quiet(session, alerting, Scope(org.id, Env.sandbox), quiet)
    return quiet


async def watch_newborns_forever(alerting: Alerting, ledger_of: Callable[[AsyncSession], CallLedger]) -> None:
    """A sweep now, and one every hour."""
    while True:
        with survived("the newborns' sweep"):
            await watch_newborns(alerting.handles.sessions, alerting, ledger_of)
        await asyncio.sleep(SWEPT_EVERY_S)
