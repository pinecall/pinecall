"""The box's test line: one sandbox number of the box's own that a person calls to reach their sandbox agent."""

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.calls import context
from pinecall_runtime.channels import service as channels
from pinecall_runtime.enums import Channel, Direction, Env
from pinecall_runtime.exceptions import ValidationError
from pinecall_runtime.kit.text import parse_e164
from pinecall_runtime.platform import service as platform
from pinecall_runtime.postgres import box_wide
from pinecall_runtime.wire.dispatch import Dispatch

# The box setting: `{"number": "+1…"}`, one of the box's own numbers routed in the sandbox.
TEST_LINE = "test_line"
NOT_A_SANDBOX_NUMBER = (
    "{number} is not a number of this box in the sandbox: the test line is one of the box's own numbers, "
    "routed in the sandbox to the agent that answers a caller it does not know"
)


async def get_test_line(session: AsyncSession) -> str | None:
    """The box's test line, or None where the operator set none."""
    value = await platform.get_setting(session, TEST_LINE)
    number = None if value is None else value.get("number")
    return number if isinstance(number, str) and number else None


async def put_test_line(session: AsyncSession, number: str | None) -> str | None:
    """Make this sandbox number the box's test line, or forget it with None; the number kept."""
    if number is None:
        await platform.delete_setting(session, TEST_LINE)
        return None
    wanted = parse_e164(number)
    with box_wide():
        route = await channels.route_at(session, Channel.phone, wanted)
    if route is None or route.env is not Env.sandbox:
        raise ValidationError(NOT_A_SANDBOX_NUMBER.format(number=wanted))
    await platform.put_setting(session, TEST_LINE, {"number": wanted})
    return wanted


# A ring at a sandbox number the job was not told the agent of: the test line is one, and whose
# agent it reaches is the caller's phone's to say.
def may_be_a_testers(dispatch: Dispatch, arrival: channels.Arrival, route: context.Route) -> bool:
    """Whether to ask whose sandbox agent this ring is for."""
    return (
        arrival.number is not None
        and dispatch.agent is None
        and arrival.direction is Direction.inbound
        and route.channel is Channel.phone
        and route.env is Env.sandbox
    )


def handed_to(route: context.Route, arrival: channels.Arrival, org: str, agent: str) -> context.Route:
    """The route a test-line ring takes once its caller is known: their org's agent, at the number dialled."""
    return context.Route(org=org, agent=agent, channel=route.channel, number=arrival.number, env=Env.sandbox)
