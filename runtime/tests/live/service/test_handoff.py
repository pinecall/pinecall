"""A call parked by a process that left is handed to the socket that takes its agent next, on any gateway."""

import asyncio
import time

import pytest

from runtime.actor import Scope
from runtime.agents.declaration import Declaration
from runtime.enums import Channel, Env
from runtime.kit.text import JsonObject
from runtime.live.parts import LiveParts
from runtime.live.peers import HANDOFFS
from runtime.live.served import OPENER_SILENT_S, Opening, Served
from runtime.live.service import handoff, openings
from runtime.wire.commands import AgentRegister
from tests.conftest import needs_the_database, until
from tests.live.sockets import Heard, an_app
from tests.session.conftest import context_of

pytestmark = needs_the_database

SCOPE = Scope("org_1", Env.sandbox)
THE_OLD_ONE = "app_old"
THE_NEW_ONE = "app_new"
# The gateways say their calls every second: by then each has heard the other, and for long enough.
HEARD_FOR_A_WHILE_S = OPENER_SILENT_S + 0.5


def started(agent: str) -> JsonObject:
    """A call.started's data, the caller unknown."""
    return {"channel": "web", "direction": "inbound", "from": "web_1", "to": agent, "caller": None, "started_at": 1.0}


async def served_on(
    live: LiveParts, call: str, agent: str, *, app: str | None = None, opened_here: bool = True
) -> Served:
    """A written call the gateway serves: bound to the socket, or parked, opened here or a copy."""
    opening = Opening(context_of(call, Channel.web), Declaration(slug=agent), SCOPE, None, owner=app)
    seen_at = None if opened_here else time.monotonic()
    served = openings.serve(live, opening, opened_here=opened_here, seen_at=seen_at)
    if opened_here:
        await served.log.append("call.started", started(agent))
    await live.calls.wait_until_heard(call)
    return served


async def took(live: LiveParts, app: str, agent: str) -> None:
    """A socket of the gateway that holds the agent and takes the calls nobody opened."""
    await live.holders.register(app, SCOPE, agent, AgentRegister(routes=[]), Declaration(slug=agent))


def attached_to(socket: Heard) -> list[str]:
    """The apps a socket was told a call was handed to."""
    return [str(entry.data["app"]) for entry in socket.of("call.attached")]


def parked(live: LiveParts) -> list[str]:
    """The calls the gateway holds for the next socket of their agent."""
    return [served.call for served in live.calls.list_parked()]


# B B2 (2026-10-23): the next `pinecall start` registered 12 s after the drain and the gateway it
# reached held none of the parked call, which another gateway held: it was never handed, its tools
# timed out and it ended as app_detached.
async def test_a_socket_that_takes_an_agent_on_another_gateway_is_handed_the_calls_parked_here(
    two_gateways: tuple[LiveParts, LiveParts], call: str, agent: str
) -> None:
    opener, other = two_gateways
    served = await served_on(opener, call, agent)
    socket = an_app(opener, THE_NEW_ONE, SCOPE)
    handoff.tell_taking(other.calls, SCOPE, agent, THE_NEW_ONE)
    await until(lambda: served.app == THE_NEW_ONE)
    await until(lambda: attached_to(socket) == [THE_NEW_ONE])
    assert call not in parked(opener)
    opener.calls.close_call(call)


# A message of the channel that cannot be read, or whose hearing raised, was an exception out of the
# listener's loop: no call was handed over on this gateway from then on.
async def test_a_handoff_that_cannot_be_read_does_not_end_the_listener(
    two_gateways: tuple[LiveParts, LiveParts], call: str, agent: str
) -> None:
    opener, other = two_gateways
    served = await served_on(opener, call, agent)
    socket = an_app(opener, THE_NEW_ONE, SCOPE)
    other.signal.publish(HANDOFFS.name, b"this is not a handoff")
    other.signal.publish(HANDOFFS.name, b'{"taking": {"app": 7}}')
    handoff.tell_taking(other.calls, SCOPE, agent, THE_NEW_ONE)
    await until(lambda: served.app == THE_NEW_ONE)
    await until(lambda: attached_to(socket) == [THE_NEW_ONE])
    opener.calls.close_call(call)


async def test_a_socket_that_takes_another_agent_or_another_scope_is_handed_nothing(
    two_gateways: tuple[LiveParts, LiveParts], call: str, agent: str
) -> None:
    opener, other = two_gateways
    served = await served_on(opener, call, agent)
    handoff.tell_taking(other.calls, Scope("org_1", Env.sandbox, "a_person"), agent, THE_NEW_ONE)
    handoff.tell_taking(other.calls, SCOPE, "somebody-else", THE_NEW_ONE)
    await asyncio.sleep(0.1)
    assert served.app is None
    opener.calls.close_call(call)


async def test_a_call_that_ended_is_not_handed_to_the_socket_that_takes_its_agent(
    live: LiveParts, call: str, agent: str
) -> None:
    """An ended call waits for its seal, which needs no socket: a call.attached after call.ended would be a lie."""
    served = await served_on(live, call, agent)
    await served.log.append(
        "call.ended", {"reason": "caller_hung_up", "ended_by": "caller", "ended_at": 2.0, "duration_s": 1.0}
    )
    await handoff.attach_parked(live.calls, SCOPE, agent, THE_NEW_ONE)
    assert served.app is None
    live.calls.close_call(call)


# The signal is lossy: the reaper's pass hands on what the message that was lost would have.
async def test_a_pass_of_the_reaper_hands_the_parked_calls_to_whoever_takes_their_agent(
    live: LiveParts, call: str, agent: str
) -> None:
    served = await served_on(live, call, agent)
    socket = an_app(live, THE_NEW_ONE, SCOPE)
    assert await handoff.hand_parked(live.calls, live.holders) == []
    await took(live, THE_NEW_ONE, agent)
    assert await handoff.hand_parked(live.calls, live.holders) == [call]
    assert served.app == THE_NEW_ONE
    await until(lambda: attached_to(socket) == [THE_NEW_ONE])
    assert await handoff.hand_parked(live.calls, live.holders) == []
    live.calls.close_call(call)


# The word of a socket leaving is lossy, and a gateway that held one can die: a call bound to a socket
# that holds its agent no more is parked by the pass, and handed on in the same one.
async def test_a_pass_of_the_reaper_parks_a_call_bound_to_a_socket_nobody_holds_any_more(
    live: LiveParts, call: str, agent: str
) -> None:
    served = await served_on(live, call, agent, app=THE_OLD_ONE)
    await took(live, THE_NEW_ONE, agent)
    an_app(live, THE_NEW_ONE, SCOPE)
    await took(live, THE_OLD_ONE, agent)
    assert await handoff.hand_parked(live.calls, live.holders) == []
    assert served.app == THE_OLD_ONE, "a call bound to a socket that holds the agent stays where it is"
    await live.holders.release(THE_OLD_ONE)
    assert await handoff.hand_parked(live.calls, live.holders) == [call]
    assert served.app == THE_NEW_ONE
    live.calls.close_call(call)


# The gateway that opened a call parks it, wherever its socket was held: the copy where the socket
# was only sends what the log holds to it, and tells the opener when the socket leaves.
async def test_a_socket_that_leaves_a_call_it_held_through_another_gateway_has_it_parked_where_it_was_opened(
    two_gateways: tuple[LiveParts, LiveParts], call: str, agent: str
) -> None:
    opener, holder = two_gateways
    served = await served_on(opener, call, agent, app=THE_OLD_ONE)
    copy = await served_on(holder, call, agent, app=THE_OLD_ONE, opened_here=False)
    assert await handoff.hand_on(holder.calls, holder.holders, THE_OLD_ONE, [copy]) == (0, 1)
    await until(lambda: served.app is None)
    assert call in parked(opener)
    assert copy.app is None
    opener.calls.close_call(call)
    holder.calls.close_call(call)


async def test_a_socket_that_leaves_a_call_hands_it_to_the_next_socket_from_the_gateway_that_opened_it(
    two_gateways: tuple[LiveParts, LiveParts], call: str, agent: str
) -> None:
    opener, holder = two_gateways
    served = await served_on(opener, call, agent, app=THE_OLD_ONE)
    copy = await served_on(holder, call, agent, app=THE_OLD_ONE, opened_here=False)
    socket = an_app(opener, THE_NEW_ONE, SCOPE)
    await took(opener, THE_NEW_ONE, agent)
    # The gateway the old socket was on answers by who it has heard holds the agent.
    await until(lambda: holder.holders.find_serving(SCOPE, agent) is not None)
    assert await handoff.hand_on(holder.calls, holder.holders, THE_OLD_ONE, [copy]) == (1, 0)
    await until(lambda: served.app == THE_NEW_ONE)
    await until(lambda: attached_to(socket) == [THE_NEW_ONE])
    opener.calls.close_call(call)
    holder.calls.close_call(call)


async def test_a_socket_that_left_a_call_already_handed_on_does_not_park_it(
    two_gateways: tuple[LiveParts, LiveParts], call: str, agent: str
) -> None:
    """The opener moved the call to another socket before the word of the first one leaving came."""
    opener, holder = two_gateways
    served = await served_on(opener, call, agent, app=THE_NEW_ONE)
    copy = await served_on(holder, call, agent, app=THE_OLD_ONE, opened_here=False)
    await handoff.hand_on(holder.calls, holder.holders, THE_OLD_ONE, [copy])
    await asyncio.sleep(0.1)
    assert served.app == THE_NEW_ONE
    opener.calls.close_call(call)
    holder.calls.close_call(call)


def a_while_on() -> float:
    """A moment by which a gateway that says nothing more from now is taken for gone."""
    return time.monotonic() + OPENER_SILENT_S + 1.0


# Production runs two gateways and a deploy replaces both: a spoken call the replaced one had opened
# went on in its worker, served by the other as a copy that no socket was ever handed. Its app heard
# no call.attached, each tool it called waited out its deadline, and it held no seat of its org.
@pytest.mark.timeout(30)
async def test_a_call_whose_opener_is_gone_is_adopted_where_its_worker_reads_and_handed_to_its_agents_socket(
    two_gateways: tuple[LiveParts, LiveParts], call: str, agent: str
) -> None:
    opener, other = two_gateways
    await served_on(opener, call, agent)
    copy = await served_on(other, call, agent, opened_here=False)
    socket = an_app(other, THE_NEW_ONE, SCOPE)
    await took(other, THE_NEW_ONE, agent)
    await until(lambda: call in other.calls.holding(SCOPE.org, SCOPE.env))
    await asyncio.sleep(HEARD_FOR_A_WHILE_S)
    with other.calls.follow(call):
        assert await handoff.adopt_orphans(other.calls, other.holders, time.monotonic()) == [], "its opener says it"
        # Asked a while on: the opener's last word of the call is old by then, as a gateway's that died.
        assert await handoff.adopt_orphans(other.calls, other.holders, a_while_on()) == [call]
        assert copy.opened_here
        assert copy.app == THE_NEW_ONE
        await until(lambda: attached_to(socket) == [THE_NEW_ONE])
        assert other.calls.holding(SCOPE.org, SCOPE.env) == [call], "one seat, though its opener's last word names it"
        assert await handoff.adopt_orphans(other.calls, other.holders, a_while_on()) == []
    opener.calls.close_call(call)
    other.calls.close_call(call)


# A copy is held by every gateway that was asked for the call: the one its worker reads from adopts it.
async def test_a_call_whose_worker_reads_from_another_gateway_is_not_adopted_here(
    two_gateways: tuple[LiveParts, LiveParts], call: str, agent: str
) -> None:
    _, other = two_gateways
    copy = await served_on(other, call, agent, opened_here=False)
    assert await handoff.adopt_orphans(other.calls, other.holders, a_while_on()) == []
    assert not copy.opened_here
    other.calls.close_call(call)


# A gateway that just started has heard nobody: every call it is asked for would look like an orphan.
async def test_a_gateway_that_just_started_adopts_nothing_until_it_has_heard_the_others(
    two_gateways: tuple[LiveParts, LiveParts], call: str, agent: str
) -> None:
    _, other = two_gateways
    copy = await served_on(other, call, agent, opened_here=False)
    with other.calls.follow(call):
        assert await handoff.adopt_orphans(other.calls, other.holders, time.monotonic()) == []
        assert not copy.opened_here
    other.calls.close_call(call)


# The signal away for a while, each gateway takes the other for gone and both may adopt one call: it
# would hold two seats of its org and be handed on twice for as long as it lasts.
@pytest.mark.timeout(30)
async def test_two_gateways_that_say_they_opened_one_call_settle_it_and_one_of_them_leaves_it(
    two_gateways: tuple[LiveParts, LiveParts], call: str, agent: str
) -> None:
    opener, other = two_gateways
    here = await served_on(opener, call, agent)
    there = await served_on(other, call, agent)
    await asyncio.sleep(HEARD_FOR_A_WHILE_S)
    for live in (opener, other):
        assert await handoff.adopt_orphans(live.calls, live.holders, time.monotonic()) == []
    assert sorted([here.opened_here, there.opened_here]) == [False, True], "a copy again on one of the two"
    opener.calls.close_call(call)
    other.calls.close_call(call)
