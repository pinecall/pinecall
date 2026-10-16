"""Quotas: an org's limits as a model, each admission on the database, and a written call cut at its last message."""

import json
import time

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from websockets.exceptions import ConnectionClosed

from pinecall_runtime.billing import service as billing
from pinecall_runtime.enums import Env
from pinecall_runtime.exceptions import QuotaExceeded, ValidationError
from tests.conftest import Gateway, Tenant, holding, needs_the_database, needs_the_services, received

NOW = time.time()


# ── the limits, as a model ──


def test_a_quota_is_a_count_and_never_negative() -> None:
    """A negative limit is refused when the quotas are made."""
    with pytest.raises(ValidationError, match="minutes cannot be -1"):
        billing.Quotas(minutes=-1)


def test_a_limit_is_reached_at_it_and_a_push_refused_only_past_it() -> None:
    """Using the limit reaches it; a push sized up front may fill it and not pass it."""
    quotas = billing.Quotas(messages=3, knowledge_chunks=10)
    assert quotas.limit_reached("messages", 2) is None
    assert quotas.limit_reached("messages", 3) == 3
    assert quotas.limit_exceeded("knowledge_chunks", 10) is None
    assert quotas.limit_exceeded("knowledge_chunks", 11) == 10


def test_a_quota_of_zero_switches_the_feature_off_and_none_is_unlimited() -> None:
    """Zero means not in the plan; no limit means as much as the org likes."""
    quotas = billing.Quotas(simulations=0)
    assert quotas.is_switched_off("simulations")
    assert not quotas.is_switched_off("minutes")
    assert quotas.limit_reached("minutes", 10**9) is None


# ── each admission, on the database ──


async def limited(sessions: async_sessionmaker[AsyncSession], tenant: Tenant, quotas: billing.Quotas) -> None:
    """The tenant's sandbox limits, replaced whole."""
    async with sessions.begin() as session:
        await billing.set_quotas(session, tenant.org, Env.sandbox, quotas)


@needs_the_database
async def test_a_call_past_the_concurrent_limit_is_refused_and_one_under_it_is_given_its_minutes(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """The ceiling of a call admitted is the org's minutes left; one more than it may run is refused."""
    await limited(sessions, tenant, billing.Quotas(concurrent_calls=2, minutes=30))
    async with sessions() as session:
        ceiling = await billing.admit_call(session, tenant.org, Env.sandbox, running=1, at=NOW)
        assert ceiling == billing.Ceiling(seconds=30 * 60, minutes=30)
        with pytest.raises(QuotaExceeded, match="2 concurrent calls in the sandbox"):
            await billing.admit_call(session, tenant.org, Env.sandbox, running=2, at=NOW)


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
        assert await billing.admit_call(session, tenant.org, Env.sandbox, running=0, at=NOW) is None


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
