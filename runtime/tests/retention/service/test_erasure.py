"""An erasure of a call or an agent: what the day's tools and slowest turns keep of a call."""

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.actor import Scope
from runtime.calls.log.store import Store
from runtime.calls.recordings import Disk
from runtime.enums import Env
from runtime.insights.models import SlowTurn, ToolDay
from runtime.retention.service import erasure
from runtime.retention.service.erasure import Erasing
from tests.calls.factories import logs_on
from tests.conftest import Tenant, needs_the_database
from tests.fakes.livekit import per_world
from tests.retention.factories import a_day_with_two_calls

pytestmark = needs_the_database


class NobodyHolds:
    """The apps holding each agent, on a box where no process holds any."""

    def is_held(self, org: str, slug: str) -> bool:
        """Nobody holds it."""
        return False


async def tools_and_turns(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> tuple[dict[str, ToolDay], set[str]]:
    """The tenant's tool days by tool, and the calls its slow turns belong to."""
    async with sessions() as session:
        tools = {row.tool: row for row in await session.scalars(select(ToolDay).where(ToolDay.org == tenant.org))}
        turns = {row.call for row in await session.scalars(select(SlowTurn).where(SlowTurn.org == tenant.org))}
    return tools, turns


async def test_erasing_a_call_deletes_its_slow_turns_and_empties_the_failure_it_left_on_a_tool(
    sessions: async_sessionmaker[AsyncSession], store: Store, tenant: Tenant, call: str, agent: str, tmp_path: Path
) -> None:
    """The day keeps its counts, which name nobody; the failure's call, moment and text go with the call."""
    first, second = await a_day_with_two_calls(sessions, tenant, call, agent)
    erasing = Erasing(Disk(tmp_path), logs_on(store).logs)
    async with sessions.begin() as session:
        await erasure.erase_call(session, erasing, Scope(tenant.org, Env.sandbox), first, by="the suite")
    tools, turns = await tools_and_turns(sessions, tenant)
    booked = tools["book_slot"]
    assert (booked.ran, booked.failed) == (2, 2)
    assert (booked.last_error_call, booked.last_error_at, booked.last_error_text) == (None, None, None)
    assert tools["find_slots"].ran == 2
    assert turns == set()
    assert second not in turns


async def test_erasing_a_call_that_did_not_leave_the_failure_keeps_it(
    sessions: async_sessionmaker[AsyncSession], store: Store, tenant: Tenant, call: str, agent: str, tmp_path: Path
) -> None:
    """Only the call the failure names empties it: erasing the other call leaves it, and the other's turns go."""
    _, second = await a_day_with_two_calls(sessions, tenant, call, agent)
    erasing = Erasing(Disk(tmp_path), logs_on(store).logs)
    async with sessions.begin() as session:
        await erasure.erase_call(session, erasing, Scope(tenant.org, Env.sandbox), second, by="the suite")
    tools, turns = await tools_and_turns(sessions, tenant)
    assert tools["book_slot"].last_error_call == call
    assert tools["book_slot"].last_error_text == "book_slot did not answer within 10s"
    assert turns == {call}


async def test_erasing_an_agent_deletes_its_days_of_tools_and_its_slow_turns(
    sessions: async_sessionmaker[AsyncSession], store: Store, tenant: Tenant, call: str, agent: str, tmp_path: Path
) -> None:
    """Every row the org keeps of the agent goes, the tool days included."""
    await a_day_with_two_calls(sessions, tenant, call, agent)
    erasing = Erasing(Disk(tmp_path), logs_on(store).logs)
    servers = per_world()
    async with sessions.begin() as session:
        await erasure.erase_agent(session, erasing, servers, NobodyHolds(), tenant.org, agent, by="the suite")
    for server in servers.values():
        await server.aclose()
    assert await tools_and_turns(sessions, tenant) == ({}, set())
