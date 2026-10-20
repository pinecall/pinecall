"""The seal's fold of a day: a call's tools and slowest turns counted once, added across calls, counted again."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinecall_runtime.agents.declaration import Versions
from pinecall_runtime.calls.models import SlowTurn, ToolDay
from pinecall_runtime.calls.repository.heads import Claim
from pinecall_runtime.calls.service import drift
from pinecall_runtime.calls.store import Store
from pinecall_runtime.enums import Env
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.wire.base import Entry
from tests.calls.factories import a_call_with_tools, a_tool_call, a_tool_result, entry
from tests.calls.folded import NOT_JUDGED, opened
from tests.conftest import Tenant, needs_the_database

pytestmark = needs_the_database


async def tools_of(sessions: async_sessionmaker[AsyncSession], tenant: Tenant) -> dict[str, ToolDay]:
    """The tenant's tool days by tool name."""
    async with sessions() as session:
        rows = await session.scalars(select(ToolDay).where(ToolDay.org == tenant.org))
        return {row.tool: row for row in rows}


async def slow_of(sessions: async_sessionmaker[AsyncSession], tenant: Tenant) -> list[SlowTurn]:
    """The tenant's slow turns, slowest first."""
    async with sessions() as session:
        rows = await session.scalars(select(SlowTurn).where(SlowTurn.org == tenant.org).order_by(SlowTurn.e2e_s.desc()))
        return list(rows)


async def test_the_seal_counts_a_calls_tools_and_slowest_turns_into_its_day(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant, call: str, agent: str
) -> None:
    """Two tools, one failing, and a slow turn with the tools between: one row each, three turns, the name."""
    await opened(sessions, tenant.org, call, agent)
    async with sessions.begin() as session:
        assert await drift.fold(session, call, a_call_with_tools(call, agent), NOT_JUDGED)
    tools = await tools_of(sessions, tenant)
    assert {name: (row.ran, row.failed) for name, row in tools.items()} == {"find_slots": (1, 0), "book_slot": (2, 2)}
    assert tools["book_slot"].last_error_text == "book_slot did not answer within 10s"
    assert (tools["find_slots"].last_error_call, tools["find_slots"].last_error_at) == (None, None)
    slow = await slow_of(sessions, tenant)
    assert [(row.seq, row.e2e_s, row.name, row.agent, row.call) for row in slow] == [
        (7, 2.0, "Marta", agent, call),
        (10, 1.5, "Marta", agent, call),
        (12, 1.2, "Marta", agent, call),
    ]
    assert (slow[0].hears_s, slow[0].thinks_s, slow[0].speaks_s) == (0.2, 0.5, 0.3)
    assert slow[0].tools_s == pytest.approx(0.6)


async def test_a_call_folded_again_adds_nothing_and_two_calls_add_with_the_newest_failure_standing(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant, call: str, agent: str
) -> None:
    """The claim keeps a second fold of the same call out; another call of the day adds and its later failure wins."""
    other = f"{call}-b"
    await opened(sessions, tenant.org, call, agent)
    await opened(sessions, tenant.org, other, agent)
    later = [
        entry(40, "tool.call", a_tool_call("tc_9", "book_slot", "s9")).model_copy(
            update={"call": other, "agent": agent}
        ),
        entry(41, "tool.result", a_tool_result("tc_9", "book_slot", error="newest")).model_copy(
            update={"call": other, "agent": agent}
        ),
    ]
    async with sessions.begin() as session:
        await drift.fold(session, call, a_call_with_tools(call, agent), NOT_JUDGED)
        await drift.fold(session, call, a_call_with_tools(call, agent), NOT_JUDGED)
    assert (await tools_of(sessions, tenant))["book_slot"].ran == 2
    async with sessions.begin() as session:
        await drift.fold(session, other, [*a_call_with_tools(other, agent), *later], NOT_JUDGED)
    booked = (await tools_of(sessions, tenant))["book_slot"]
    assert (booked.ran, booked.failed) == (5, 5)
    assert (booked.last_error_call, booked.last_error_text) == (other, "newest")
    assert sum(booked.buckets) == 2
    assert len(await slow_of(sessions, tenant)) == 6


async def test_a_rebuild_forgets_the_days_and_counts_the_sealed_calls_again_from_their_logs(
    sessions: async_sessionmaker[AsyncSession], store: Store, tenant: Tenant, call: str, agent: str
) -> None:
    """The rebuild is idempotent: the same rows after it, however many times it runs."""
    await store.claim(call, agent, tenant.org, Claim(Scope(tenant.org, Env.sandbox), Versions(config=1)))
    entries: list[Entry] = [*a_call_with_tools(call, agent), entry(15, "call.score", NOT_JUDGED.dump())]
    for kept in entries:
        await store.append(call, agent, kept.type, kept.data, ephemeral=False)
    await store.writer.drain()
    await store.seal(call)
    for _ in range(2):
        async with sessions.begin() as session:
            done = await drift.rebuild(session, org=tenant.org, since=None)
        assert (done.calls, done.folded) == (1, 1)
        tools = await tools_of(sessions, tenant)
        assert {name: row.ran for name, row in tools.items()} == {"find_slots": 1, "book_slot": 2}
        assert [row.seq for row in await slow_of(sessions, tenant)] == [7, 10, 12]
