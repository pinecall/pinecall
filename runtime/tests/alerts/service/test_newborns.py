"""A newborn org a day old with no call that went well is pointed at once, to the operators, and never again."""

from datetime import datetime, timedelta

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.accounts.models import Org
from runtime.accounts.service import people
from runtime.accounts.service.key_cache import KeyCache
from runtime.actor import Scope
from runtime.alerts.service.alerts import Alerting, list_alerts
from runtime.alerts.service.newborns import watch_newborns
from runtime.calls.models.call_fact import CallFact
from runtime.calls.models.call_log_head import CallLogHead
from runtime.calls.service.lists import list_ended_calls
from runtime.enums import Env
from runtime.kit.time import now
from runtime.mail.service.outbox import Outbox
from runtime.wire.events import VendorFailed
from tests.alerts.factories import ADDRESS, VAULT, WrittenLogs
from tests.conftest import Tenant, make_tenant, needs_the_database
from tests.fakes.smtp import Relay, text_of


async def an_ended_call(session: AsyncSession, tenant: Tenant, call: str) -> None:
    """One call of the org's that ended, as its head and its facts hold it."""
    session.add(
        CallLogHead(log=call, agent="front-desk", call=call, started_at=1.0, org=tenant.org, env=Env.sandbox, holder="")
    )
    session.add(CallFact(call=call, ended_at=40.0))
    await session.flush()


# Every test shares the database, and a sweep reads every org born in the week before it: an org born
# now would be pointed at by whichever test swept first. Each test's orgs are born at a moment no other
# test sweeps, and its sweeps are told the time from there.
async def born(sessions: async_sessionmaker[AsyncSession], days_from_now: int, *tenants: Tenant) -> datetime:
    """Move the orgs' birth to a moment of this test's own; that moment."""
    at = now() + timedelta(days=days_from_now)
    async with sessions.begin() as session:
        await session.execute(update(Org).where(Org.id.in_([each.org for each in tenants])).values(created_at=at))
    return at


async def operating(
    sessions: async_sessionmaker[AsyncSession], key_cache: KeyCache, tenant: Tenant, *, on: bool
) -> None:
    """Make the tenant's admin one who runs the box, or take it back."""
    async with sessions.begin() as session:
        admin = await people.find_person(session, f"admin@{tenant.slug}.test")
        assert admin is not None
        await people.set_operator(session, key_cache, admin, on=on)


@needs_the_database
async def test_a_newborn_whose_every_call_a_vendor_failed_is_pointed_at_once(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant, call: str
) -> None:
    """A day old, one ended call a vendor failed: org.quiet kept once with the counts; the next sweeps say nothing."""
    logs = WrittenLogs()
    scope = Scope(tenant.org, Env.sandbox)
    birth = await born(sessions, 100, tenant)
    failed = VendorFailed(
        call=call,
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
        alerting = Alerting(logs, outbox, ADDRESS)
        async with sessions.begin() as session:
            await an_ended_call(session, tenant, call)
            await alerting.raise_alert(session, scope, "front-desk", failed)
        # Too young: nothing yet.
        young = await watch_newborns(sessions, alerting, list_ended_calls, at=birth + timedelta(hours=1))
        assert tenant.org not in young
        pointed = await watch_newborns(sessions, alerting, list_ended_calls, at=birth + timedelta(days=2))
        assert pointed == [tenant.org]
        again = await watch_newborns(sessions, alerting, list_ended_calls, at=birth + timedelta(days=3))
        assert tenant.org not in again
        await outbox.drain()
    # No agent's log: nothing written on one. Nobody of the org mailed: the org's admin never hears it.
    assert [kind for _, kind, _ in logs.written] == ["vendor.failed"]
    assert all("quiet" not in email["Subject"] for email in relay.to(f"admin@{tenant.slug}.test"))
    async with sessions() as session:
        kept = await list_alerts(session, scope)
    quiet = [row for row in kept if row.kind == "org.quiet"]
    assert len(quiet) == 1
    assert (quiet[0].agent, quiet[0].subject, quiet[0].data["calls"], quiet[0].data["failed"]) == (
        None,
        tenant.org,
        1,
        1,
    )


@needs_the_database
async def test_a_newborn_with_a_call_that_went_well_is_left_alone(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant, call: str
) -> None:
    """One ended call nobody failed: the org is not quiet."""
    birth = await born(sessions, 200, tenant)
    async with Relay() as relay:
        outbox = Outbox(sessions, VAULT, relay.mailbox)
        alerting = Alerting(WrittenLogs(), outbox, ADDRESS)
        async with sessions.begin() as session:
            await an_ended_call(session, tenant, call)
        pointed = await watch_newborns(sessions, alerting, list_ended_calls, at=birth + timedelta(days=2))
        await outbox.drain()
    assert pointed == []
    async with sessions() as session:
        kept = await list_alerts(session, Scope(tenant.org, Env.sandbox))
    assert [row.kind for row in kept] == []


# A launch day is hundreds of newborn orgs: mailed one by one, the operators read none of them.
@needs_the_database
async def test_the_quiet_newborns_of_one_sweep_are_one_mail_to_the_operators(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant, key_cache: KeyCache
) -> None:
    other = await make_tenant(sessions)
    birth = await born(sessions, 300, tenant, other)
    await operating(sessions, key_cache, tenant, on=True)
    try:
        async with Relay() as relay:
            outbox = Outbox(sessions, VAULT, relay.mailbox)
            alerting = Alerting(WrittenLogs(), outbox, ADDRESS)
            pointed = await watch_newborns(sessions, alerting, list_ended_calls, at=birth + timedelta(days=2))
            await outbox.drain()
    finally:
        await operating(sessions, key_cache, tenant, on=False)
    assert set(pointed) == {tenant.org, other.org}
    (digest,) = [email for email in relay.to(f"admin@{tenant.slug}.test") if "quiet" in email["Subject"]]
    said = text_of(digest)
    assert tenant.org in said and other.org in said
    assert f"{ADDRESS}/box/orgs" in said
    assert [email for email in relay.to(f"admin@{other.slug}.test") if "quiet" in email["Subject"]] == []
