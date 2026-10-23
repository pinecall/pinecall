"""The alerts kept: each one written as it is raised, read newest first, and forgotten past 90 days."""

from collections.abc import Sequence
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.alerts.models import Alert
from pinecall_runtime.alerts.repository import AlertRepository
from pinecall_runtime.alerts.service.telling import subject_of
from pinecall_runtime.enums import Env
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.kit.crypto import random_id
from pinecall_runtime.kit.text import JsonObject
from pinecall_runtime.kit.time import now
from pinecall_runtime.postgres import box_wide

ID_PREFIX = "alr_"
# What a read answers at most, and unless asked for fewer.
MOST_READ = 200
READ = 50
# How long an alert is kept: the nightly retention forgets one older.
KEPT_DAYS = 90


async def keep_alert(
    session: AsyncSession, scope: Scope, agent: str | None, kind: str, data: JsonObject, *, mailed: bool
) -> Alert:
    """Write the alert as it was raised, and whether it was mailed."""
    row = Alert(
        id=random_id(ID_PREFIX, 8),
        org=scope.org,
        env=scope.env,
        agent=agent,
        kind=kind,
        subject=subject_of(kind, data),
        data=dict(data),
        mailed=mailed,
        at=now(),
    )
    return await AlertRepository(session).add(row)


async def alerts_of(
    session: AsyncSession, scope: Scope, *, limit: int = READ, before: datetime | None = None
) -> Sequence[Alert]:
    """The org's alerts in the env, newest first."""
    return await AlertRepository(session).newest(scope.org, scope.env, limit=min(limit, MOST_READ), before=before)


async def every_orgs_alerts(
    session: AsyncSession,
    *,
    org: str | None = None,
    env: Env | None = None,
    limit: int = READ,
    before: datetime | None = None,
) -> Sequence[Alert]:
    """Every org's alerts, or one org's, newest first: the box's to read."""
    with box_wide():
        return await AlertRepository(session).newest(org, env, limit=min(limit, MOST_READ), before=before)


async def forget_alerts(session: AsyncSession, at: datetime) -> int:
    """Forget every alert older than KEPT_DAYS; how many."""
    with box_wide():
        return await AlertRepository(session).forget_before(at - timedelta(days=KEPT_DAYS))
