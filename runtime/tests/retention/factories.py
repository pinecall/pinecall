"""A day of an agent's calls as the retention tests find it: folded into its tools' days and its slowest turns."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.calls.factories import a_call_with_tools, a_tool_result, entry
from tests.conftest import Tenant
from tests.insights.folded import fold_call


async def a_day_with_two_calls(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant, call: str, agent: str
) -> tuple[str, str]:
    """Marta's call, whose failure is the day's last, and a later call of the same agent that only worked."""
    first = await fold_call(sessions, tenant.org, a_call_with_tools(call, agent))
    worked = entry(40, "tool.result", a_tool_result("tc_9", "find_slots", seconds=0.1))
    second = await fold_call(sessions, tenant.org, [worked.model_copy(update={"call": f"{call}-b", "agent": agent})])
    return first, second
