"""A call parked by a process that left is handed to the socket that takes its agent next, on any gateway."""

import asyncio
from collections.abc import AsyncIterator

import pytest

from pinecall_runtime.agents.declaration import AgentConfig
from pinecall_runtime.agents.service.registry import AgentRegistry
from pinecall_runtime.calls.logs import Log, Logs
from pinecall_runtime.calls.service.binding import Handoffs, attach_parked, hand_on, hand_parked
from pinecall_runtime.calls.service.live import Live, Served
from pinecall_runtime.calls.service.peers import HANDOFF_CHANNEL, Handoff, Taking, tell_handoff
from pinecall_runtime.calls.service.tool_calls import ToolCalls
from pinecall_runtime.calls.store import Store
from pinecall_runtime.enums import Channel, Env
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.redis import LocalSignal
from pinecall_runtime.wire.base import Entry
from pinecall_runtime.wire.commands import AgentRegister
from tests.conftest import needs_the_database, until
from tests.session.conftest import context_of

pytestmark = needs_the_database

SCOPE = Scope("org_1", Env.sandbox)
THE_OLD_ONE = "app_old"
THE_NEW_ONE = "app_new"


async def nothing_before(_call_id: str) -> None:
    return None


def started(agent: str) -> dict[str, object]:
    """A call.started's data, the caller unknown."""
    return {"channel": "web", "direction": "inbound", "from": "web_1", "to": agent, "caller": None, "started_at": 1.0}


async def served_on(
    live: Live, store: Store, call: str, agent: str, *, app: str | None = None, opened_here: bool = True
) -> Served:
    """A written call this gateway serves: bound to the socket, or parked, opened here or a copy."""
    log = Log(store, call, agent)
    if opened_here:
        await log.append("call.started", started(agent))
    config = AgentConfig(slug=agent)
    live.serve(
        Served(
            agent=agent,
            scope=SCOPE,
            app=app,
            log=log,
            commands=asyncio.Queue(),
            context=context_of(call, Channel.web),
            config=config,
            tools=ToolCalls(config, log, nothing_before, nothing_before),
            opened_here=opened_here,
        )
    )
    await live.commands_heard(call)
    return live.calls[call]


def socket_of(live: Live, app: str) -> list[Entry]:
    """An app socket on this gateway, collecting what is sent down it."""
    sent: list[Entry] = []

    async def send(entry: Entry) -> None:
        sent.append(entry)

    live.sockets[app] = send
    return sent


async def took(registry: AgentRegistry, app: str, agent: str) -> None:
    """A socket that holds the agent and takes the calls nobody opened."""
    await registry.register(app, SCOPE, agent, AgentRegister(routes=[]))


def attached_to(sent: list[Entry]) -> list[str]:
    """The apps a socket was told a call was handed to."""
    return [str(entry.data["app"]) for entry in sent if entry.type == "call.attached"]


@pytest.fixture
async def gateways(store: Store) -> AsyncIterator[tuple[Live, Live, AgentRegistry, Handoffs]]:
    """Two gateways on one signal, the registry they share, and the first's ear for what the other says."""
    signal = LocalSignal()
    opener, other = Live(signal), Live(signal)
    registry = AgentRegistry(signal, Logs(store))
    handoffs = Handoffs(opener, registry)
    await handoffs.start()
    await until(lambda: bool(signal._listening.get(HANDOFF_CHANNEL)))
    yield opener, other, registry, handoffs
    await handoffs.close()


# B B2 (2026-10-23): the next `pinecall start` registered 12 s after the drain and the gateway it
# reached held none of the parked call, which another gateway held: it was never handed, its tools
# timed out and it ended as app_detached.
async def test_a_socket_that_takes_an_agent_on_another_gateway_is_handed_the_calls_parked_here(
    gateways: tuple[Live, Live, AgentRegistry, Handoffs], store: Store, call: str, agent: str
) -> None:
    opener, other, _, _ = gateways
    await served_on(opener, store, call, agent)
    sent = socket_of(opener, THE_NEW_ONE)
    tell_handoff(other.signal, Handoff(taking=Taking(app=THE_NEW_ONE, scope=SCOPE, agent=agent)))
    await until(lambda: opener.calls[call].app == THE_NEW_ONE)
    await until(lambda: attached_to(sent) == [THE_NEW_ONE])
    assert call not in opener.parked_since
    opener.close_call(call)


# A message of the channel that cannot be read, or whose hearing raised, was an exception out of the
# listener's loop: no call was handed over on this gateway from then on.
async def test_a_handoff_that_cannot_be_read_does_not_end_the_listener(
    gateways: tuple[Live, Live, AgentRegistry, Handoffs], store: Store, call: str, agent: str
) -> None:
    opener, other, _, _ = gateways
    await served_on(opener, store, call, agent)
    sent = socket_of(opener, THE_NEW_ONE)
    other.signal.publish(HANDOFF_CHANNEL, b"this is not a handoff")
    other.signal.publish(HANDOFF_CHANNEL, b'{"taking": {"app": 7}}')
    tell_handoff(other.signal, Handoff(taking=Taking(app=THE_NEW_ONE, scope=SCOPE, agent=agent)))
    await until(lambda: opener.calls[call].app == THE_NEW_ONE)
    await until(lambda: attached_to(sent) == [THE_NEW_ONE])
    opener.close_call(call)


async def test_a_socket_that_takes_another_agent_or_another_scope_is_handed_nothing(
    gateways: tuple[Live, Live, AgentRegistry, Handoffs], store: Store, call: str, agent: str
) -> None:
    opener, other, _, _ = gateways
    await served_on(opener, store, call, agent)
    mine = Scope("org_1", Env.sandbox, "a_person")
    tell_handoff(other.signal, Handoff(taking=Taking(app=THE_NEW_ONE, scope=mine, agent=agent)))
    tell_handoff(other.signal, Handoff(taking=Taking(app=THE_NEW_ONE, scope=SCOPE, agent="somebody-else")))
    await asyncio.sleep(0.1)
    assert opener.calls[call].app is None
    opener.close_call(call)


async def test_a_call_that_ended_is_not_handed_to_the_socket_that_takes_its_agent(
    gateways: tuple[Live, Live, AgentRegistry, Handoffs], store: Store, call: str, agent: str
) -> None:
    """An ended call waits for its seal, which needs no socket: a call.attached after call.ended would be a lie."""
    opener, _, _, _ = gateways
    served = await served_on(opener, store, call, agent)
    await served.log.append(
        "call.ended", {"reason": "caller_hung_up", "ended_by": "caller", "ended_at": 2.0, "duration_s": 1.0}
    )
    await attach_parked(opener, SCOPE, agent, THE_NEW_ONE)
    assert opener.calls[call].app is None
    opener.close_call(call)


# The signal is lossy: the reaper's pass hands on what the message that was lost would have.
async def test_a_pass_of_the_reaper_hands_the_parked_calls_to_whoever_takes_their_agent(
    gateways: tuple[Live, Live, AgentRegistry, Handoffs], store: Store, call: str, agent: str
) -> None:
    opener, _, registry, _ = gateways
    await served_on(opener, store, call, agent)
    sent = socket_of(opener, THE_NEW_ONE)
    assert await hand_parked(opener, registry) == []
    await took(registry, THE_NEW_ONE, agent)
    assert await hand_parked(opener, registry) == [call]
    assert opener.calls[call].app == THE_NEW_ONE
    await until(lambda: attached_to(sent) == [THE_NEW_ONE])
    assert await hand_parked(opener, registry) == []
    opener.close_call(call)


# The word of a socket leaving is lossy, and a gateway that held one can die: a call bound to a socket
# the registry no longer holds is parked by the pass, and handed on in the same one.
async def test_a_pass_of_the_reaper_parks_a_call_bound_to_a_socket_nobody_holds_any_more(
    gateways: tuple[Live, Live, AgentRegistry, Handoffs], store: Store, call: str, agent: str
) -> None:
    opener, _, registry, _ = gateways
    await served_on(opener, store, call, agent, app=THE_OLD_ONE)
    await took(registry, THE_NEW_ONE, agent)
    socket_of(opener, THE_NEW_ONE)
    await took(registry, THE_OLD_ONE, agent)
    assert await hand_parked(opener, registry) == []
    assert opener.calls[call].app == THE_OLD_ONE, "a call bound to a socket that holds the agent stays where it is"
    await registry.release(THE_OLD_ONE)
    assert await hand_parked(opener, registry) == [call]
    assert opener.calls[call].app == THE_NEW_ONE
    opener.close_call(call)


# The gateway that opened a call parks it, wherever its socket was held: the copy where the socket
# was only sends what the log holds to it, and tells the opener when the socket leaves.
async def test_a_socket_that_leaves_a_call_it_held_through_another_gateway_has_it_parked_where_it_was_opened(
    gateways: tuple[Live, Live, AgentRegistry, Handoffs], store: Store, call: str, agent: str
) -> None:
    opener, holder, registry, _ = gateways
    await served_on(opener, store, call, agent, app=THE_OLD_ONE)
    await served_on(holder, store, call, agent, app=THE_OLD_ONE, opened_here=False)
    assert await hand_on(holder, registry, [call], left=THE_OLD_ONE) == (0, 1)
    await until(lambda: opener.calls[call].app is None)
    assert call in opener.parked_since
    assert holder.calls[call].app is None
    opener.close_call(call)
    holder.close_call(call)


async def test_a_socket_that_leaves_a_call_hands_it_to_the_next_socket_from_the_gateway_that_opened_it(
    gateways: tuple[Live, Live, AgentRegistry, Handoffs], store: Store, call: str, agent: str
) -> None:
    opener, holder, registry, _ = gateways
    await served_on(opener, store, call, agent, app=THE_OLD_ONE)
    await served_on(holder, store, call, agent, app=THE_OLD_ONE, opened_here=False)
    sent = socket_of(opener, THE_NEW_ONE)
    await took(registry, THE_NEW_ONE, agent)
    assert await hand_on(holder, registry, [call], left=THE_OLD_ONE) == (1, 0)
    await until(lambda: opener.calls[call].app == THE_NEW_ONE)
    await until(lambda: attached_to(sent) == [THE_NEW_ONE])
    opener.close_call(call)
    holder.close_call(call)


async def test_a_socket_that_left_a_call_already_handed_on_does_not_park_it(
    gateways: tuple[Live, Live, AgentRegistry, Handoffs], store: Store, call: str, agent: str
) -> None:
    """The opener moved the call to another socket before the word of the first one leaving came."""
    opener, holder, registry, _ = gateways
    await served_on(opener, store, call, agent, app=THE_NEW_ONE)
    await served_on(holder, store, call, agent, app=THE_OLD_ONE, opened_here=False)
    await hand_on(holder, registry, [call], left=THE_OLD_ONE)
    await asyncio.sleep(0.1)
    assert opener.calls[call].app == THE_NEW_ONE
    opener.close_call(call)
    holder.close_call(call)
