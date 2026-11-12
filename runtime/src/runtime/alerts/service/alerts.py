"""An alert of the org's: raised on the agent's log, kept, mailed, left for the webhooks; listed, and forgotten."""

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.actor import Scope
from runtime.alerts.models import Alert
from runtime.alerts.repository import AlertRepository
from runtime.alerts.service import kinds
from runtime.alerts.service.mail import mail_alert
from runtime.enums import Env
from runtime.exceptions import QuotaExceeded
from runtime.kit.crypto import random_id
from runtime.kit.text import JsonObject
from runtime.kit.time import now
from runtime.mail import service as mail
from runtime.postgres import BoxSession
from runtime.wire.base import WireModel
from runtime.wire.events import CreditsExhausted

ID_PREFIX = "alr_"
# What a read answers at most, and unless asked for fewer.
MOST_READ = 200
READ = 50
# How long an alert is kept: the nightly retention forgets one older.
KEPT_DAYS = 90


class AgentLog(Protocol):
    """One agent's log, as an alert is written on it."""

    async def append(self, kind: str, data: JsonObject | None = None) -> object:
        """One entry on the log."""
        ...


class Logs(Protocol):
    """The logs an alert is written to: calls' are above alerts, so they are handed in."""

    def agent(self, slug: str) -> AgentLog:
        """The agent's own log."""
        ...


# Built once by the gateway, when what is above alerts exists to be handed in. A detector (a monitor
# read at a seal, the spend, the newborns' sweep) and every domain that raises an alert of its own is
# given this, and the session of the transaction the alert belongs to.
class Alerting:
    """What raises an org's alerts: the agents' logs, the outbox, and the address its emails open the console at."""

    def __init__(self, logs: Logs, outbox: mail.Outbox, address: str | None) -> None:
        self.logs = logs
        self.outbox = outbox
        self.address = address

    # Kept whatever else it reaches: a webhook is an org's choice, and an alert nobody set one for is
    # still mailed and still listed. Nothing here waits on anything outside the box: the emails leave
    # once the caller's transaction commits, and the row, written with `posted_at` empty, is what the
    # gateways' loop posts to the webhooks (`webhooks.post_pending`). The log's entry comes last, so an
    # alert whose row could not be written is on no log.
    async def raise_alert(self, session: AsyncSession, scope: Scope, agent: str | None, alert: WireModel) -> bool:
        """Keep the alert, mail it, and write it on the agent's log when it is one agent's; False when already said."""
        kind = kinds.kind_of(alert)
        subject = kind.subject(alert)
        ours = await claim_alert(session, scope, kind, subject)
        if kind.once_since is not None and not ours:
            return False
        mailed = ours and await mail_alert(session, self.outbox, self.address, scope, kind, alert)
        row = Alert(
            id=random_id(ID_PREFIX, 8),
            org=scope.org,
            env=scope.env,
            agent=agent,
            kind=kind.name,
            subject=subject,
            data=alert.dump(),
            mailed=mailed,
            at=now(),
            posted_at=None,
        )
        await AlertRepository(session).add(row)
        if agent is not None:
            await self.logs.agent(agent).append(kind.name.value, row.data)
        return True

    # A caller about to raise the refusal says this in a transaction of its own (`sessions.begin()`):
    # its request's is rolled back, and an alert the refusal took with it was never kept. `pinecall
    # alerts` did not list it, and the hourly mail, which looks for the one before it, was sent again
    # with every refusal.
    async def credits_exhausted(self, session: AsyncSession, scope: Scope, agent: str, refused: QuotaExceeded) -> bool:
        """Say on the agent's log, by mail and to the webhooks that one of the org's quotas ran out."""
        alert = CreditsExhausted.model_validate(
            {
                "org": scope.org,
                "quota": refused.quota,
                "used": refused.used,
                "limit": refused.limit,
                "calls": list(refused.calls),
            }
        )
        return await self.raise_alert(session, scope, agent, alert)


# The one "already said" of every kind. Until 2026-11 there were four: a monitor's own row, a scan of
# the calls' log for `spend.unusual` (a read and then a write, so two calls of an org sealing together
# said it twice), the alerts kept and a lock for a quiet org, and the mail's cap of once an hour, read
# and then written the same way. The lock is taken first by every kind: a kind said once is said by
# whoever holds it and finds nothing kept, and the mail's cap is read by its holder alone, so a burst
# of refusals mails once.
async def claim_alert(session: AsyncSession, scope: Scope, kind: kinds.Kind[Any], subject: str) -> bool:
    """Take the right to say this kind and subject to the org now; False when it was said, or is being said."""
    repository = AlertRepository(session)
    if not await repository.claim(scope.org, kind.name, subject):
        return False
    if kind.once_since is None:
        return True
    return not await repository.has_said_since(scope.org, kind.name, subject, kind.once_since(now()))


async def list_alerts(
    session: AsyncSession, scope: Scope, *, limit: int = READ, before: datetime | None = None
) -> Sequence[Alert]:
    """The org's alerts in the env, newest first."""
    return await AlertRepository(session).list_newest(scope.org, scope.env, limit=min(limit, MOST_READ), before=before)


async def list_every_orgs_alerts(
    session: BoxSession,
    *,
    org: str | None = None,
    env: Env | None = None,
    limit: int = READ,
    before: datetime | None = None,
) -> Sequence[Alert]:
    """Every org's alerts, or one org's, newest first: the box's to read."""
    return await AlertRepository(session).list_newest(org, env, limit=min(limit, MOST_READ), before=before)


async def forget_alerts(session: BoxSession, at: datetime) -> int:
    """Forget every alert older than KEPT_DAYS; how many."""
    return await AlertRepository(session).delete_before(at - timedelta(days=KEPT_DAYS))
