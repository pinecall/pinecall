"""The box's test line: one sandbox number of the box's own that a person calls to reach their sandbox agent."""

from collections.abc import Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.accounts import service as accounts
from runtime.actor import Scope
from runtime.enums import Channel, Env
from runtime.exceptions import ValidationError
from runtime.kit.text import parse_e164
from runtime.platform import service as platform
from runtime.scoping import box_wide
from runtime.telephony.repository import RouteRepository
from runtime.telephony.service.hand_over import AgentsHeld
from runtime.wire.worker import RingAtTestLine

NOT_A_SANDBOX_NUMBER = (
    "{number} is not a number of this box in the sandbox: the test line is one of the box's own numbers, "
    "routed in the sandbox to the agent that answers a caller it does not know"
)


def _load(value: Mapping[str, Any]) -> str | None:
    number = value.get("number")
    return number if isinstance(number, str) and number else None


def _dump(number: str | None) -> dict[str, Any]:
    return {"number": number}


# The box setting: `{"number": "+1…"}`, one of the box's own numbers routed in the sandbox.
TEST_LINE: platform.Setting[str | None] = platform.Setting("test_line", _load, _dump)


async def find_test_line(session: AsyncSession) -> str | None:
    """The box's test line, or None where the operator set none."""
    return await platform.find_setting(session, TEST_LINE)


async def put_test_line(session: AsyncSession, number: str | None) -> str | None:
    """Make this sandbox number the box's test line, or forget it with None; the number kept."""
    if number is None:
        await platform.delete_setting(session, TEST_LINE)
        return None
    wanted = parse_e164(number)
    with box_wide():
        route = await RouteRepository(session).find_at(Channel.phone, wanted)
    if route is None or route.env is not Env.sandbox:
        raise ValidationError(NOT_A_SANDBOX_NUMBER.format(number=wanted))
    await platform.put_setting(session, TEST_LINE, wanted)
    return wanted


# A ring at the box's test line is already in the sandbox: the worker that took it runs the call
# as the caller's org's, in whichever copy takes a ring from that phone. The org alone: the phone is
# a member's, but they named no agent and the org holds several. The org and the agent, no holder:
# nobody holds that agent in the sandbox right now.
async def ring_at(session: AsyncSession, held: AgentsHeld, *, number: str, caller: str) -> RingAtTestLine:
    """Whose sandbox agent a ring at the box's test line is for: the org, the agent and the copy, or nobody's."""
    if parse_e164(number) != await find_test_line(session):
        return RingAtTestLine()
    try:
        phone = parse_e164(caller)
    except ValidationError:
        # A withheld number is nobody's.
        return RingAtTestLine()
    member = await accounts.find_member_by_test_phone(session, phone)
    if member is None:
        return RingAtTestLine()
    # The agent a phone reaches when its person named none: the one the org holds, if it holds one.
    unclaimed = held.list_taking_unclaimed(member.org, Env.sandbox)
    agent = member.test_agent or (next(iter(unclaimed)) if len(unclaimed) == 1 else None)
    if agent is None:
        return RingAtTestLine(org=member.org)
    holder = held.find_ring_holder(Scope(member.org, Env.sandbox), agent, caller)
    return RingAtTestLine(org=member.org, agent=agent, holder=holder)
