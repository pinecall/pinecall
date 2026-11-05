"""A newborn org a day old with no call that went well is pointed at once, to the operators, and never again."""

import os
from datetime import timedelta

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinecall_runtime.accounts.service import members
from pinecall_runtime.alerts.service.delivery import raise_alert
from pinecall_runtime.alerts.service.kept import alerts_of
from pinecall_runtime.alerts.service.newborns import watch_newborns
from pinecall_runtime.calls.models import CallFact, CallLogHead
from pinecall_runtime.calls.repository.facts import FactsRepository
from pinecall_runtime.config import load_settings
from pinecall_runtime.enums import Env
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.kit.crypto import Vault
from pinecall_runtime.kit.handles import Handles
from pinecall_runtime.kit.time import now
from pinecall_runtime.redis import LocalSignal
from pinecall_runtime.wire.events import VendorFailed
from tests.alerts.test_delivery import Alerting, Posted, WrittenLogs
from tests.conftest import Tenant, make_tenant, needs_the_database
from tests.fakes.livekit import per_world
from tests.fakes.webhooks import Receiver

VAULT = Vault(os.environ["PINECALL_VAULT_KEY"])


async def an_ended_call(session: AsyncSession, tenant: Tenant, call: str) -> None:
    """One call of the org's that ended, as its head and its facts hold it."""
    session.add(
        CallLogHead(log=call, agent="front-desk", call=call, started_at=1.0, org=tenant.org, env=Env.sandbox, holder="")
    )
    session.add(CallFact(call=call, ended_at=40.0))
    await session.flush()


@needs_the_database
async def test_a_newborn_whose_every_call_a_vendor_failed_is_pointed_at_once(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """A day old, one ended call a vendor failed: org.quiet kept once with the counts; the next sweeps say nothing."""
    logs, outbox = WrittenLogs(), Posted()
    scope = Scope(tenant.org, Env.sandbox)
    servers = per_world()
    async with httpx.AsyncClient(transport=httpx.MockTransport(Receiver().answer)) as http:
        alerting = Alerting(Handles(load_settings(), VAULT, http, servers, LocalSignal(), sessions), logs, outbox)
        failed = VendorFailed(
            call="call_quiet_1",
            stage="llm",
            vendor="google",
            model=None,
            code="component_failed",
            message="504",
            own_key=True,
            errors=2,
        )
        async with sessions.begin() as session:
            await an_ended_call(session, tenant, "call_quiet_1")
            await raise_alert(session, alerting, scope, "front-desk", failed)
        # Too young: nothing yet.
        young = await watch_newborns(sessions, alerting, FactsRepository, at=now() + timedelta(hours=1))
        assert tenant.org not in young
        pointed = await watch_newborns(sessions, alerting, FactsRepository, at=now() + timedelta(days=2))
        assert tenant.org in pointed
        again = await watch_newborns(sessions, alerting, FactsRepository, at=now() + timedelta(days=3))
        assert tenant.org not in again
    for server in servers.values():
        await server.aclose()
    # No agent's log: nothing written on one. Nobody of the org mailed: the org's admin never hears it.
    assert [kind for _, kind, _ in logs.written] == ["vendor.failed"]
    assert all(email.to != f"admin@{tenant.slug}.test" or "quiet" not in email.subject for _, email in outbox.sent)
    async with sessions() as session:
        kept = await alerts_of(session, scope)
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
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """One ended call nobody failed: the org is not quiet."""
    logs, outbox = WrittenLogs(), Posted()
    servers = per_world()
    async with httpx.AsyncClient(transport=httpx.MockTransport(Receiver().answer)) as http:
        alerting = Alerting(Handles(load_settings(), VAULT, http, servers, LocalSignal(), sessions), logs, outbox)
        async with sessions.begin() as session:
            await an_ended_call(session, tenant, "call_well_1")
        pointed = await watch_newborns(sessions, alerting, FactsRepository, at=now() + timedelta(days=2))
    for server in servers.values():
        await server.aclose()
    assert tenant.org not in pointed
    async with sessions() as session:
        kept = await alerts_of(session, Scope(tenant.org, Env.sandbox))
    assert [row.kind for row in kept] == []


# A launch day is hundreds of newborn orgs: mailed one by one, the operators read none of them.
@needs_the_database
async def test_the_quiet_newborns_of_one_sweep_are_one_mail_to_the_operators(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    other = await make_tenant(sessions)
    logs, outbox = WrittenLogs(), Posted()
    servers = per_world()
    async with sessions.begin() as session:
        await members.set_operator(session, tenant.org, tenant.member, on=True)
    async with httpx.AsyncClient(transport=httpx.MockTransport(Receiver().answer)) as http:
        alerting = Alerting(Handles(load_settings(), VAULT, http, servers, LocalSignal(), sessions), logs, outbox)
        pointed = await watch_newborns(sessions, alerting, FactsRepository, at=now() + timedelta(days=2))
    for server in servers.values():
        await server.aclose()
    assert {tenant.org, other.org} <= set(pointed)
    digests = [email for _, email in outbox.sent if "quiet" in email.subject]
    assert [email.to for email in digests] == [f"admin@{tenant.slug}.test"], "one mail, to the operator alone"
    assert tenant.org in digests[0].text and other.org in digests[0].text
    async with sessions.begin() as session:
        await members.set_operator(session, tenant.org, tenant.member, on=False)
