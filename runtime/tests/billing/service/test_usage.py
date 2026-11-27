"""What a call spends: the month's totals the admissions read, written and rebuilt."""

from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.actor import Scope
from runtime.billing.service import usage
from runtime.calls import service as calls
from runtime.calls.log.store import Store
from runtime.calls.models import Opener
from runtime.enums import Env
from runtime.kit.text import JsonObject
from runtime.kit.time import month_of
from tests.calls.factories import a_summary
from tests.conftest import Tenant, Ticking, needs_the_database

# ── what a call spends: the totals the admissions read ──


# Every entry of a test is stamped by its store's clock, which starts at the second the test began:
# what its calls spent is in that month.
@pytest.fixture
def this_month(ticking: Ticking) -> date:
    """The month the test's clock started in: the one its calls spend in."""
    return month_of(ticking.first)


async def summarised(store: Store, tenant: Tenant, agent: str, call: str, opened_by: Opener | None) -> None:
    """A call of the tenant's two minutes and eight turns, opened by this opener, and its summary."""
    async with store.sessions.begin() as session:
        await calls.claim_call(session, call, agent, calls.Claim(Scope(tenant.org, Env.sandbox), opened_by=opened_by))
    await store.write("entry", call, agent, "call.summary", a_summary([]))
    await store.writer.drain()


@needs_the_database
async def test_a_written_call_spends_messages_and_no_minutes_and_a_spoken_one_minutes_and_no_messages(
    sessions: async_sessionmaker[AsyncSession], store: Store, tenant: Tenant, agent: str, call: str, this_month: date
) -> None:
    """J F9: one quota for each kind of call; the gateway opens the written ones."""
    await summarised(store, tenant, agent, f"{call}-chat", Opener.gateway)
    async with sessions() as session:
        written = await usage.get_usage(session, tenant.org, Env.sandbox, this_month)
    assert (written.calls, written.minutes, written.messages) == (1, 0.0, 8)
    await summarised(store, tenant, agent, f"{call}-voice", Opener.fleet)
    async with sessions() as session:
        both = await usage.get_usage(session, tenant.org, Env.sandbox, this_month)
    assert (both.calls, both.minutes, both.messages) == (2, 2.0, 8)
    await summarised(store, tenant, agent, f"{call}-app", Opener.app)
    async with sessions() as session:
        three = await usage.get_usage(session, tenant.org, Env.sandbox, this_month)
    assert (three.calls, three.minutes, three.messages) == (3, 4.0, 8)


@needs_the_database
async def test_a_call_opened_before_heads_said_who_opened_it_spends_both_as_it_always_did(
    sessions: async_sessionmaker[AsyncSession], store: Store, tenant: Tenant, agent: str, call: str, this_month: date
) -> None:
    await summarised(store, tenant, agent, call, None)
    async with sessions() as session:
        old = await usage.get_usage(session, tenant.org, Env.sandbox, this_month)
    assert (old.calls, old.minutes, old.messages) == (1, 2.0, 8)


@needs_the_database
async def test_a_rebuild_counts_a_written_call_as_the_triggers_did(
    sessions: async_sessionmaker[AsyncSession], store: Store, tenant: Tenant, agent: str, call: str, this_month: date
) -> None:
    """The recount reads the head's opener too, so a rebuilt month agrees with the one that was written."""
    await summarised(store, tenant, agent, f"{call}-chat", Opener.gateway)
    await summarised(store, tenant, agent, f"{call}-voice", Opener.fleet)
    async with sessions.begin() as session:
        await usage.rebuild_usage_totals(session)
    async with sessions() as session:
        rebuilt = await usage.get_usage(session, tenant.org, Env.sandbox, this_month)
    assert (rebuilt.calls, rebuilt.minutes, rebuilt.messages) == (2, 2.0, 8)


@needs_the_database
async def test_a_flows_model_spends_one_message_its_tokens_and_its_cost_on_the_agents_log(
    sessions: async_sessionmaker[AsyncSession], store: Store, tenant: Tenant, agent: str, this_month: date
) -> None:
    """An extract step's request is written on the agent's own log, whose head names no env: its data says it."""
    async with sessions.begin() as session:
        await calls.claim_agent_log(session, agent, tenant.org)
    usage_rows = [
        {"type": "llm_usage", "provider": "google", "model": "flash-lite", "input_tokens": 3080, "output_tokens": 60}
    ]
    spent: JsonObject = {
        "kind": "extract",
        "app": "front-desk-app",
        "flow": "notice",
        "run": "run_8f4a2c",
        "env": "sandbox",
        "turns": 1,
        "usage": usage_rows,
        "cost": {"usd": 0.0011, "rows": [], "unpriced": []},
    }
    await store.write("entry", None, agent, "model.spent", spent)
    await store.writer.drain()
    async with sessions() as session:
        used = await usage.get_usage(session, tenant.org, Env.sandbox, this_month)
    assert (used.calls, used.minutes, used.messages, used.llm_tokens) == (0, 0.0, 1, 3140)
    assert used.cost_usd == pytest.approx(0.0011)
