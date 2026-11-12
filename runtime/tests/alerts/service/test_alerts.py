"""An alert raised: kept every time, mailed to the admins once an hour per subject, and left for a pass of the posts."""

import json
from datetime import timedelta

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.actor import Scope
from runtime.alerts.models import Alert
from runtime.alerts.service.alerts import KEPT_DAYS, Alerting, forget_alerts, list_alerts
from runtime.alerts.service.webhooks import post_pending
from runtime.enums import Env
from runtime.kit.time import now
from runtime.mail.service.outbox import Outbox
from runtime.postgres import BoxSession
from runtime.wire.events import VendorFailed
from tests.alerts.factories import A_FAILED_APP, ADDRESS, VAULT, WrittenLogs
from tests.conftest import Tenant, needs_the_database
from tests.fakes.smtp import Relay, text_of
from tests.fakes.webhooks import Receiver


@needs_the_database
async def test_an_alert_is_kept_every_time_and_mailed_to_the_admins_once_an_hour(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    logs = WrittenLogs()
    scope = Scope(tenant.org, Env.sandbox)
    async with Relay() as relay:
        outbox = Outbox(sessions, VAULT, relay.mailbox)
        alerting = Alerting(logs, outbox, ADDRESS)
        # Within the hour, the same app three times: kept three times, mailed the first.
        for _ in range(3):
            async with sessions.begin() as session:
                assert await alerting.raise_alert(session, scope, None, A_FAILED_APP)
        await outbox.drain()
    assert logs.written == [], "an app's alert is on no agent's log"
    (mailed,) = relay.to(f"admin@{tenant.slug}.test")
    assert mailed["Subject"] == "support went down · The suite's org (sandbox)"
    said = text_of(mailed)
    assert "secrets: 403" in said and "more lines" not in said
    assert f"{ADDRESS}/sandbox/settings/alerts" in said
    async with sessions() as session:
        kept = await list_alerts(session, scope)
    assert [(row.kind, row.subject, row.mailed) for row in kept] == [
        ("app.failed", "support", False),
        ("app.failed", "support", False),
        ("app.failed", "support", True),
    ]


@needs_the_database
async def test_an_alert_rolled_back_with_its_transaction_is_neither_kept_nor_mailed(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    scope = Scope(tenant.org, Env.sandbox)
    async with Relay() as relay:
        outbox = Outbox(sessions, VAULT, relay.mailbox)
        async with sessions() as session:
            await Alerting(WrittenLogs(), outbox, ADDRESS).raise_alert(session, scope, None, A_FAILED_APP)
            await session.rollback()
        await outbox.drain()
    assert relay.to(f"admin@{tenant.slug}.test") == []
    async with sessions() as session:
        assert await list_alerts(session, scope) == []


@needs_the_database
async def test_an_alert_of_one_agent_is_written_on_that_agents_log_as_it_is_kept(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    logs = WrittenLogs()
    failed = VendorFailed(
        call="call_1d6b",
        stage="llm",
        vendor="google",
        model=None,
        code="component_failed",
        message="504",
        own_key=True,
        errors=2,
    )
    async with Relay() as relay:
        outbox = Outbox(sessions, VAULT, relay.mailbox)
        async with sessions.begin() as session:
            await Alerting(logs, outbox, None).raise_alert(session, Scope(tenant.org), "front-desk", failed)
        await outbox.drain()
    assert logs.written == [("front-desk", "vendor.failed", failed.dump())]
    (mailed,) = relay.to(f"admin@{tenant.slug}.test")
    assert mailed["Subject"] == "google failed a call · The suite's org (production)"
    assert "Open the console" not in text_of(mailed), "a box with no address mails no link"


# The row is the outbox of the webhooks: written with no post yet, and marked by the pass that takes
# it, this one's or a gateway's of the same database, so no pass takes it again.
@needs_the_database
async def test_an_alert_kept_is_taken_by_a_pass_of_the_posts_once(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    receiver = Receiver()
    async with Relay() as relay:
        outbox = Outbox(sessions, VAULT, relay.mailbox)
        async with sessions.begin() as session:
            await Alerting(WrittenLogs(), outbox, ADDRESS).raise_alert(session, Scope(tenant.org), None, A_FAILED_APP)
        await outbox.drain()
    async with httpx.AsyncClient(transport=httpx.MockTransport(receiver.answer)) as http:
        await post_pending(sessions, VAULT, http)
        async with sessions() as session:
            (taken_at,) = (await session.execute(select(Alert.posted_at).where(Alert.org == tenant.org))).scalars()
        assert taken_at is not None
        await post_pending(sessions, VAULT, http)
    async with sessions() as session:
        (still,) = (await session.execute(select(Alert.posted_at).where(Alert.org == tenant.org))).scalars()
    assert still == taken_at
    of_the_org = [post for post in receiver.heard if json.loads(post.content)["org"] == tenant.org]
    assert of_the_org == [], "an org that named no URL, on a box whose operator named none, is posted nowhere"


@needs_the_database
async def test_an_alert_past_its_days_is_forgotten_and_a_newer_one_kept(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    scope = Scope(tenant.org, Env.production)
    async with Relay() as relay:
        outbox = Outbox(sessions, VAULT, relay.mailbox)
        alerting = Alerting(WrittenLogs(), outbox, ADDRESS)
        async with sessions.begin() as session:
            await alerting.raise_alert(session, scope, None, A_FAILED_APP)
            await alerting.raise_alert(session, scope, None, A_FAILED_APP)
        await outbox.drain()
    async with sessions.begin() as session:
        (newest, oldest) = await list_alerts(session, scope)
        aged = now() - timedelta(days=KEPT_DAYS + 1)
        await session.execute(update(Alert).where(Alert.id == oldest.id).values(at=aged))
    async with sessions.begin() as session:
        assert await forget_alerts(BoxSession(session), now()) >= 1
        left = (await session.execute(select(Alert.id).where(Alert.org == tenant.org))).scalars().all()
    assert left == [newest.id]
