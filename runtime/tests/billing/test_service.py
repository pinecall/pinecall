"""Quotas: an org's limits as a model, each admission on the database, and a written call cut at its last message."""

import json
import time
from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from websockets.exceptions import ConnectionClosed

from pinecall_runtime.billing import service as billing
from pinecall_runtime.calls.repository.heads import Claim
from pinecall_runtime.calls.store import Store
from pinecall_runtime.enums import Env, Opener
from pinecall_runtime.exceptions import QuotaExceeded, ValidationError
from pinecall_runtime.kit.auth import Scope
from tests.calls.factories import a_summary
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
        assert await billing.admit_call(session, tenant.org, Env.sandbox, running=0, at=NOW) is None


# ── what the org is shown: every limit it was given ──


@needs_the_services
async def test_the_limits_an_org_reads_are_every_one_an_operator_can_set_with_what_is_used_of_each(
    sessions: async_sessionmaker[AsyncSession], gateway: Gateway, tenant: Tenant
) -> None:
    """C B6: the budget, the hosted apps, the memory and the knowledge were limits `pinecall limits` never showed."""
    given = billing.Quotas(memory_facts=500, knowledge_chunks=2000, hosted_apps=3, budget_usd=60, minutes=30)
    await limited(sessions, tenant, given)
    answer = (await gateway.http.get("/v1/limits", headers=tenant.server)).json()
    for quota in billing.QUOTA_NAMES:
        assert set(answer[quota]) == {"limit", "used"}, quota
    assert answer["budget_usd"] == {"limit": 60, "used": 0.0}
    assert (answer["memory_facts"], answer["knowledge_chunks"], answer["hosted_apps"]) == (
        {"limit": 500, "used": 0},
        {"limit": 2000, "used": 0},
        {"limit": 3, "used": 0},
    )
    assert answer["agents"]["limit"] is None


# ── what a call spends: the totals the admissions read ──

# The store's clock ticks from 1.0, so every entry of these tests falls in the first month of 1970.
THE_FIRST_MONTH = date(1970, 1, 1)


async def summarised(store: Store, tenant: Tenant, agent: str, call: str, opened_by: Opener) -> None:
    """A call of the tenant's two minutes and eight turns, opened by this opener, and its summary."""
    await store.claim(call, agent, tenant.org, Claim(Scope(tenant.org, Env.sandbox), opened_by=opened_by))
    await store.append(call, agent, "call.summary", a_summary([]), ephemeral=False)
    await store.writer.drain()


@needs_the_database
async def test_a_written_call_spends_messages_and_no_minutes_and_a_spoken_one_minutes_and_no_messages(
    sessions: async_sessionmaker[AsyncSession], store: Store, tenant: Tenant, agent: str, call: str
) -> None:
    """J F9: one quota for each kind of call; the gateway opens the written ones."""
    await summarised(store, tenant, agent, f"{call}-chat", Opener.gateway)
    async with sessions() as session:
        written = await billing.get_usage(session, tenant.org, Env.sandbox, THE_FIRST_MONTH)
    assert (written.calls, written.minutes, written.messages) == (1, 0.0, 8)
    await summarised(store, tenant, agent, f"{call}-voice", Opener.fleet)
    async with sessions() as session:
        both = await billing.get_usage(session, tenant.org, Env.sandbox, THE_FIRST_MONTH)
    assert (both.calls, both.minutes, both.messages) == (2, 2.0, 8)
    await summarised(store, tenant, agent, f"{call}-app", Opener.app)
    async with sessions() as session:
        three = await billing.get_usage(session, tenant.org, Env.sandbox, THE_FIRST_MONTH)
    assert (three.calls, three.minutes, three.messages) == (3, 4.0, 8)


@needs_the_database
async def test_a_call_opened_before_heads_said_who_opened_it_spends_both_as_it_always_did(
    sessions: async_sessionmaker[AsyncSession], store: Store, tenant: Tenant, agent: str, call: str
) -> None:
    await store.claim(call, agent, tenant.org, Claim(Scope(tenant.org, Env.sandbox)))
    await store.append(call, agent, "call.summary", a_summary([]), ephemeral=False)
    await store.writer.drain()
    async with sessions() as session:
        old = await billing.get_usage(session, tenant.org, Env.sandbox, THE_FIRST_MONTH)
    assert (old.calls, old.minutes, old.messages) == (1, 2.0, 8)


@needs_the_database
async def test_a_rebuild_counts_a_written_call_as_the_triggers_did(
    sessions: async_sessionmaker[AsyncSession], store: Store, tenant: Tenant, agent: str, call: str
) -> None:
    """The recount reads the head's opener too, so a rebuilt month agrees with the one that was written."""
    await summarised(store, tenant, agent, f"{call}-chat", Opener.gateway)
    await summarised(store, tenant, agent, f"{call}-voice", Opener.fleet)
    async with sessions.begin() as session:
        await billing.rebuild_usage_totals(session)
    async with sessions() as session:
        rebuilt = await billing.get_usage(session, tenant.org, Env.sandbox, THE_FIRST_MONTH)
    assert (rebuilt.calls, rebuilt.minutes, rebuilt.messages) == (2, 2.0, 8)


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
