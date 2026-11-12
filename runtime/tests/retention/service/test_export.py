"""An org's export: a line for each of its tools' days and each of its slowest turns."""

import json

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.enums import Env
from runtime.retention.service.export import export_lines
from tests.conftest import Tenant, needs_the_database
from tests.retention.factories import a_day_with_two_calls

pytestmark = needs_the_database


async def test_an_orgs_export_carries_its_tool_days_and_its_slow_turns(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant, call: str, agent: str
) -> None:
    """A line each: the tool's day with its newest failure, the turn with the caller's name."""
    await a_day_with_two_calls(sessions, tenant, call, agent)
    lines = [json.loads(line) async for line in export_lines(sessions, tenant.org, Env.sandbox)]
    days = {line["tool"]: line for line in lines if line["kind"] == "tool_day"}
    assert (days["book_slot"]["ran"], days["book_slot"]["last_error_call"]) == (2, call)
    turns = [line for line in lines if line["kind"] == "slow_turn"]
    assert sorted(line["seq"] for line in turns) == [7, 10, 12]
    assert {line["name"] for line in turns} == {"Marta"}
