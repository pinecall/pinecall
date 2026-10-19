"""An erasure of a call or an agent, and the export: what the day's tools and slowest turns keep of a call."""

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinecall_runtime.calls.models import SlowTurn, ToolDay
from pinecall_runtime.calls.recordings import Disk
from pinecall_runtime.enums import Env
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.retention.service import erasure
from pinecall_runtime.retention.service.export import export_lines
from tests.calls.factories import a_call_with_tools, a_tool_result, entry
from tests.calls.folded import fold_call
from tests.conftest import Tenant, needs_the_database

pytestmark = needs_the_database


async def a_day_with_two_calls(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant, call: str, agent: str
) -> tuple[str, str]:
    """Marta's call, whose failure is the day's last, and a later call of the same agent that only worked."""
    first = await fold_call(sessions, tenant.org, a_call_with_tools(call, agent))
    worked = entry(40, "tool.result", a_tool_result("tc_9", "find_slots", seconds=0.1))
    second = await fold_call(sessions, tenant.org, [worked.model_copy(update={"call": f"{call}-b", "agent": agent})])
    return first, second


async def tools_and_turns(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> tuple[dict[str, ToolDay], set[str]]:
    """The tenant's tool days by tool, and the calls its slow turns belong to."""
    async with sessions() as session:
        tools = {row.tool: row for row in await session.scalars(select(ToolDay).where(ToolDay.org == tenant.org))}
        turns = {row.call for row in await session.scalars(select(SlowTurn).where(SlowTurn.org == tenant.org))}
    return tools, turns


async def test_erasing_a_call_deletes_its_slow_turns_and_empties_the_failure_it_left_on_a_tool(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant, call: str, agent: str, tmp_path: Path
) -> None:
    """The day keeps its counts, which name nobody; the failure's call, moment and text go with the call."""
    first, second = await a_day_with_two_calls(sessions, tenant, call, agent)
    async with sessions.begin() as session:
        await erasure.erase_call(session, Disk(tmp_path), Scope(tenant.org, Env.sandbox), first, by="the suite")
    tools, turns = await tools_and_turns(sessions, tenant)
    booked = tools["book_slot"]
    assert (booked.ran, booked.failed) == (2, 2)
    assert (booked.last_error_call, booked.last_error_at, booked.last_error_text) == (None, None, None)
    assert tools["find_slots"].ran == 2
    assert turns == set()
    assert second not in turns


async def test_erasing_a_call_that_did_not_leave_the_failure_keeps_it(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant, call: str, agent: str, tmp_path: Path
) -> None:
    """Only the call the failure names empties it: erasing the other call leaves it, and the other's turns go."""
    _, second = await a_day_with_two_calls(sessions, tenant, call, agent)
    async with sessions.begin() as session:
        await erasure.erase_call(session, Disk(tmp_path), Scope(tenant.org, Env.sandbox), second, by="the suite")
    tools, turns = await tools_and_turns(sessions, tenant)
    assert tools["book_slot"].last_error_call == call
    assert tools["book_slot"].last_error_text == "book_slot did not answer within 10s"
    assert turns == {call}


async def test_erasing_an_agent_deletes_its_days_of_tools_and_its_slow_turns(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant, call: str, agent: str, tmp_path: Path
) -> None:
    """Every row the org keeps of the agent goes, the tool days included."""
    await a_day_with_two_calls(sessions, tenant, call, agent)
    async with sessions.begin() as session:
        await erasure.erase_agent(session, Disk(tmp_path), tenant.org, agent, by="the suite")
    assert await tools_and_turns(sessions, tenant) == ({}, set())


async def test_an_orgs_export_carries_its_tool_days_and_its_slow_turns(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant, call: str, agent: str
) -> None:
    """A line each: the tool's day with its newest failure, the turn with the caller's name."""
    await a_day_with_two_calls(sessions, tenant, call, agent)
    async with sessions() as session:
        lines = [json.loads(line) async for line in export_lines(session, tenant.org, Env.sandbox)]
    days = {line["tool"]: line for line in lines if line["kind"] == "tool_day"}
    assert (days["book_slot"]["ran"], days["book_slot"]["last_error_call"]) == (2, call)
    turns = [line for line in lines if line["kind"] == "slow_turn"]
    assert sorted(line["seq"] for line in turns) == [7, 10, 12]
    assert {line["name"] for line in turns} == {"Marta"}
