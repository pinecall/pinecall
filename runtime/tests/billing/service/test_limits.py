"""Each admission on the database, and a written call cut at its last message or refused a seat."""

import json
import time

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from websockets.exceptions import ConnectionClosed

from runtime.billing import service as billing
from runtime.billing.service import quotas
from runtime.billing.service.limits import SeatsTaken
from runtime.enums import Env
from runtime.exceptions import QuotaExceeded
from tests.conftest import Gateway, Tenant, holding, needs_the_database, needs_the_services, received

NOW = time.time()


# ── each admission, on the database ──


async def limited(sessions: async_sessionmaker[AsyncSession], tenant: Tenant, given: billing.Quotas) -> None:
    """The tenant's sandbox limits, replaced whole."""
    async with sessions.begin() as session:
        await quotas.put_quotas(session, tenant.org, Env.sandbox, given)


@needs_the_database
async def test_a_call_past_the_concurrent_limit_is_refused_and_one_under_it_is_given_its_minutes(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """The ceiling of a call admitted is the org's minutes left; one more than it may run is refused."""
    await limited(sessions, tenant, billing.Quotas(concurrent_calls=2, minutes=30))
    async with sessions() as session:
        ceiling = await billing.admit_call(session, tenant.org, Env.sandbox, running=["call_a"], at=NOW)
        assert ceiling == billing.Ceiling(seconds=30 * 60, minutes=30)
        with pytest.raises(SeatsTaken, match="2 concurrent calls in the sandbox: call_a, call_b still open") as refused:
            await billing.admit_call(session, tenant.org, Env.sandbox, running=["call_a", "call_b"], at=NOW)
        assert refused.value.calls == ("call_a", "call_b")
        assert "end them in the console's Calls" in str(refused.value)


@needs_the_database
async def test_a_simulation_is_refused_when_the_ones_that_ended_and_the_ones_on_the_line_fill_the_limit(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """H F3: a simulation is counted when it is admitted, so those begun and not ended weigh as those ended."""
    await limited(sessions, tenant, billing.Quotas(simulations=2))
    async with sessions() as session:
        await billing.admit_simulation(session, tenant.org, Env.sandbox, at=NOW, playing=1)
        with pytest.raises(QuotaExceeded, match="2 of its 2 simulations in the sandbox") as refused:
            await billing.admit_simulation(session, tenant.org, Env.sandbox, at=NOW, playing=2)
    assert (refused.value.quota, refused.value.limit) == ("simulations", 2)


@needs_the_database
async def test_a_turn_past_the_orgs_messages_is_refused_naming_the_quota(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """A written call's turns count against the org's messages, the call's own included."""
    await limited(sessions, tenant, billing.Quotas(messages=3))
    async with sessions() as session:
        await billing.admit_turn(session, tenant.org, Env.sandbox, turns=2, tokens=0, at=NOW)
        with pytest.raises(QuotaExceeded) as refused:
            await billing.admit_turn(session, tenant.org, Env.sandbox, turns=3, tokens=0, at=NOW)
    assert refused.value.quota == "messages"


@needs_the_database
async def test_a_push_that_would_pass_the_chunks_is_refused_whole(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """A base is pushed whole or not at all: one chunk past the limit refuses the push."""
    await limited(sessions, tenant, billing.Quotas(knowledge_chunks=100))
    async with sessions() as session:
        await billing.admit_push(session, tenant.org, Env.sandbox, keeping=100)
        with pytest.raises(QuotaExceeded, match="101 of its 100 knowledge chunks"):
            await billing.admit_push(session, tenant.org, Env.sandbox, keeping=101)


@needs_the_database
async def test_an_org_without_limits_is_admitted_without_a_ceiling(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """No minutes, messages or tokens set: the call runs as long as it runs."""
    await limited(sessions, tenant, billing.Quotas())
    async with sessions() as session:
        assert await billing.admit_call(session, tenant.org, Env.sandbox, running=[], at=NOW) is None


# ── a written call, end to end ──


@needs_the_services
async def test_a_written_call_is_cut_with_the_reason_when_the_org_spends_its_messages(
    sessions: async_sessionmaker[AsyncSession], gateway: Gateway, tenant: Tenant
) -> None:
    """The org may send one message: the first line is answered, the second ends the call saying why."""
    await limited(sessions, tenant, billing.Quotas(messages=1))
    agent = f"agent-{tenant.slug}"
    async with holding(gateway, tenant, agent), gateway.socket(f"/v1/chat?agent={agent}", tenant.server) as chat:
        await received(chat, "call.started")
        await chat.send(json.dumps({"text": "hola"}))
        await received(chat, "turn.agent")
        await chat.send(json.dumps({"text": "otra cosa"}))
        with pytest.raises(ConnectionClosed) as closed:
            while True:
                await chat.recv()
    assert closed.value.rcvd is not None
    assert "messages" in closed.value.rcvd.reason


@needs_the_services
async def test_a_written_call_refused_for_the_orgs_seats_is_said_on_the_agents_log_as_any_refusal_is(
    sessions: async_sessionmaker[AsyncSession], gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    """H F2: the 429 of a call past `concurrent_calls` writes credits.exhausted, as minutes and messages do."""
    await limited(sessions, tenant, billing.Quotas(concurrent_calls=1))
    async with holding(gateway, tenant, agent), gateway.socket(f"/v1/chat?agent={agent}", tenant.server) as first:
        await received(first, "call.started")
        async with gateway.socket(f"/v1/chat?agent={agent}", tenant.server) as second:
            with pytest.raises(ConnectionClosed) as refused:
                await second.recv()
        assert refused.value.rcvd is not None
        assert refused.value.rcvd.code == 4429
        assert "1 of its 1 concurrent calls" in refused.value.rcvd.reason
        answer = await gateway.http.get(
            f"/v1/agents/{agent}/calls", headers={**tenant.server, "accept": "application/json"}
        )
    said = [entry["data"] for entry in answer.json()["entries"] if entry["type"] == "credits.exhausted"]
    assert [(one["quota"], one["used"], one["limit"]) for one in said] == [("concurrent_calls", 1, 1)]
    # Kept too: the refusal rolled its own transaction back, and the alert was written in another.
    listed = (await gateway.http.get("/v1/alerts", headers=tenant.person)).json()["alerts"]
    assert [(one["kind"], one["agent"]) for one in listed] == [("credits.exhausted", agent)]
