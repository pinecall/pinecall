"""What a call spends: the month's totals the admissions read, written and rebuilt."""

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.actor import Scope
from runtime.billing.service import usage
from runtime.calls import service as calls
from runtime.calls.log.store import Store
from runtime.calls.models import Opener
from runtime.enums import Env
from tests.calls.factories import a_summary
from tests.conftest import Tenant, needs_the_database

# ── what a call spends: the totals the admissions read ──

# The store's clock ticks from 1.0, so every entry of these tests falls in the first month of 1970.
THE_FIRST_MONTH = date(1970, 1, 1)


async def summarised(store: Store, tenant: Tenant, agent: str, call: str, opened_by: Opener | None) -> None:
    """A call of the tenant's two minutes and eight turns, opened by this opener, and its summary."""
    async with store.sessions.begin() as session:
        await calls.claim_call(session, call, agent, calls.Claim(Scope(tenant.org, Env.sandbox), opened_by=opened_by))
    await store.write("entry", call, agent, "call.summary", a_summary([]))
    await store.writer.drain()


@needs_the_database
async def test_a_written_call_spends_messages_and_no_minutes_and_a_spoken_one_minutes_and_no_messages(
    sessions: async_sessionmaker[AsyncSession], store: Store, tenant: Tenant, agent: str, call: str
) -> None:
    """J F9: one quota for each kind of call; the gateway opens the written ones."""
    await summarised(store, tenant, agent, f"{call}-chat", Opener.gateway)
    async with sessions() as session:
        written = await usage.get_usage(session, tenant.org, Env.sandbox, THE_FIRST_MONTH)
    assert (written.calls, written.minutes, written.messages) == (1, 0.0, 8)
    await summarised(store, tenant, agent, f"{call}-voice", Opener.fleet)
    async with sessions() as session:
        both = await usage.get_usage(session, tenant.org, Env.sandbox, THE_FIRST_MONTH)
    assert (both.calls, both.minutes, both.messages) == (2, 2.0, 8)
    await summarised(store, tenant, agent, f"{call}-app", Opener.app)
    async with sessions() as session:
        three = await usage.get_usage(session, tenant.org, Env.sandbox, THE_FIRST_MONTH)
    assert (three.calls, three.minutes, three.messages) == (3, 4.0, 8)


@needs_the_database
async def test_a_call_opened_before_heads_said_who_opened_it_spends_both_as_it_always_did(
    sessions: async_sessionmaker[AsyncSession], store: Store, tenant: Tenant, agent: str, call: str
) -> None:
    await summarised(store, tenant, agent, call, None)
    async with sessions() as session:
        old = await usage.get_usage(session, tenant.org, Env.sandbox, THE_FIRST_MONTH)
    assert (old.calls, old.minutes, old.messages) == (1, 2.0, 8)


@needs_the_database
async def test_a_rebuild_counts_a_written_call_as_the_triggers_did(
    sessions: async_sessionmaker[AsyncSession], store: Store, tenant: Tenant, agent: str, call: str
) -> None:
    """The recount reads the head's opener too, so a rebuilt month agrees with the one that was written."""
    await summarised(store, tenant, agent, f"{call}-chat", Opener.gateway)
    await summarised(store, tenant, agent, f"{call}-voice", Opener.fleet)
    async with sessions.begin() as session:
        await usage.rebuild_usage_totals(session)
    async with sessions() as session:
        rebuilt = await usage.get_usage(session, tenant.org, Env.sandbox, THE_FIRST_MONTH)
    assert (rebuilt.calls, rebuilt.minutes, rebuilt.messages) == (2, 2.0, 8)
