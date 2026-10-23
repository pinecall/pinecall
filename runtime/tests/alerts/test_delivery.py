"""An alert raised: kept always, mailed to the admins once an hour per subject, posted where a webhook is set."""

import json
import os
from dataclasses import dataclass, field
from datetime import timedelta

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinecall_runtime.accounts.service.emails import Email
from pinecall_runtime.alerts.models import Alert
from pinecall_runtime.alerts.service.delivery import raise_alert
from pinecall_runtime.alerts.service.kept import KEPT_DAYS, alerts_of, forget_alerts
from pinecall_runtime.alerts.service.webhooks import (
    Webhook,
    delete_operator_webhook,
    put_operator_webhook,
    put_webhook,
)
from pinecall_runtime.config import load_settings
from pinecall_runtime.enums import Env
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.kit.crypto import Vault
from pinecall_runtime.kit.handles import Handles
from pinecall_runtime.kit.text import JsonObject
from pinecall_runtime.kit.time import now
from pinecall_runtime.redis import LocalSignal
from pinecall_runtime.wire.feed import AppFailed
from tests.conftest import Tenant, needs_the_database
from tests.fakes.livekit import per_world
from tests.fakes.webhooks import Receiver

VAULT = Vault(os.environ["PINECALL_VAULT_KEY"])
OPERATORS_URL = "https://hooks.example.test/alerts?the-operator"


class WrittenLogs:
    """The agents' logs as the alert sees them: every entry appended, by agent."""

    def __init__(self) -> None:
        """No agent written yet."""
        self.written: list[tuple[str, str, JsonObject | None]] = []

    def agent(self, slug: str) -> "WrittenLogs.Log":
        """The agent's own log."""
        return WrittenLogs.Log(self, slug)

    class Log:
        """One agent's log, appending into the record."""

        def __init__(self, logs: "WrittenLogs", slug: str) -> None:
            """The log of one agent."""
            self.logs, self.slug = logs, slug

        async def append(self, kind: str, data: JsonObject | None = None) -> object:
            """One entry kept."""
            self.logs.written.append((self.slug, kind, data))
            return None


@dataclass
class Posted:
    """The outbox as the alert sees it: every email handed over, and from whose mailbox."""

    sent: list[tuple[str | None, Email]] = field(default_factory=list[tuple[str | None, Email]])

    async def post(self, org: str | None, email: Email) -> bool:
        """Kept, as sent."""
        self.sent.append((org, email))
        return True


@dataclass
class Alerting:
    """What raising an alert reaches, as the gateway's Serving holds it."""

    handles: Handles
    logs: WrittenLogs
    outbox: Posted


@needs_the_database
async def test_an_alert_is_kept_mailed_to_the_admins_once_an_hour_and_posted_where_a_webhook_is_set(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    receiver, logs, outbox = Receiver(), WrittenLogs(), Posted()
    scope = Scope(tenant.org, Env.sandbox)
    failed = AppFailed(app="support", host="support-r4-e8033b63", release=4, why="secrets: 403\nmore lines")
    servers = per_world()
    async with httpx.AsyncClient(transport=httpx.MockTransport(receiver.answer)) as http:
        alerting = Alerting(Handles(load_settings(), VAULT, http, servers, LocalSignal(), sessions), logs, outbox)
        # No webhook anywhere: kept and mailed all the same.
        async with sessions.begin() as session:
            await raise_alert(session, alerting, scope, None, failed)
        assert receiver.heard == []
        # Within the hour, the same app again: kept, not mailed again; the org's webhook hears it.
        async with sessions.begin() as session:
            await put_webhook(session, VAULT, tenant.org, Webhook(url=receiver.url))
            await raise_alert(session, alerting, scope, None, failed)
        # The operator's webhook hears it too, the same body.
        async with sessions.begin() as session:
            await put_operator_webhook(session, VAULT, Webhook(url=OPERATORS_URL, secret="ops-secret"))
            await raise_alert(session, alerting, scope, None, failed)
            await delete_operator_webhook(session)
    for server in servers.values():
        await server.aclose()
    assert logs.written == []
    mine = [email for org, email in outbox.sent if org == tenant.org]
    (mailed,) = mine
    assert mailed.to == f"admin@{tenant.slug}.test"
    assert mailed.subject == "support went down · The suite's org (sandbox)"
    assert "secrets: 403" in mailed.text and "more lines" not in mailed.text
    to_the_org = [posted for posted in receiver.heard if str(posted.url) == receiver.url]
    to_the_operator = [posted for posted in receiver.heard if str(posted.url) == OPERATORS_URL]
    assert (len(to_the_org), len(to_the_operator)) == (2, 1)
    body = json.loads(to_the_operator[0].content)
    assert (body["type"], body["org"], body["env"], body["agent"]) == ("app.failed", tenant.org, "sandbox", None)
    assert to_the_operator[0].headers["x-pinecall-signature"].startswith("sha256=")
    async with sessions() as session:
        kept = await alerts_of(session, scope)
    assert [(row.kind, row.subject, row.mailed) for row in kept] == [
        ("app.failed", "support", False),
        ("app.failed", "support", False),
        ("app.failed", "support", True),
    ]


@needs_the_database
async def test_an_alert_past_its_days_is_forgotten_and_a_newer_one_kept(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    scope = Scope(tenant.org, Env.production)
    logs, outbox = WrittenLogs(), Posted()
    failed = AppFailed(app="support", host="support-r1-aaaaaaaa", release=1, why="exited")
    servers = per_world()
    async with httpx.AsyncClient(transport=httpx.MockTransport(Receiver().answer)) as http:
        alerting = Alerting(Handles(load_settings(), VAULT, http, servers, LocalSignal(), sessions), logs, outbox)
        async with sessions.begin() as session:
            await raise_alert(session, alerting, scope, None, failed)
            await raise_alert(session, alerting, scope, None, failed)
    for server in servers.values():
        await server.aclose()
    async with sessions.begin() as session:
        (newest, oldest) = await alerts_of(session, scope)
        aged = now() - timedelta(days=KEPT_DAYS + 1)
        await session.execute(update(Alert).where(Alert.id == oldest.id).values(at=aged))
    async with sessions.begin() as session:
        assert await forget_alerts(session, now()) >= 1
        left = (await session.execute(select(Alert.id).where(Alert.org == tenant.org))).scalars().all()
    assert left == [newest.id]
