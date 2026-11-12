"""The calls a gateway serves: a refused command is answered, the stream goes on, a caller's hang-up ends the call."""

import asyncio
from typing import cast, override

from pinecall_runtime.agents.declaration import AgentConfig
from pinecall_runtime.calls.logs import Log
from pinecall_runtime.calls.service.live import Live, Served
from pinecall_runtime.calls.service.peers import CALLER_HUNG_UP, COMMANDS_CHANNEL, send_command
from pinecall_runtime.calls.service.tool_calls import ToolCalls
from pinecall_runtime.calls.store import Store
from pinecall_runtime.enums import Channel, Env
from pinecall_runtime.exceptions import PinecallError
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.redis import LocalSignal
from pinecall_runtime.session import service as session
from pinecall_runtime.wire.base import Command, Entry, WireModel
from pinecall_runtime.wire.commands import RoomSend
from tests.conftest import needs_the_database
from tests.session.conftest import AGENT, context_of

APP = "app_1"
NO_ROOM = "room.send acts on a call's line, and this call is written"


class Written:
    """A written call's session as the stream sees it: it takes every command but a room's."""

    def __init__(self) -> None:
        """Nothing applied yet, and the call going on."""
        self.applied: list[WireModel] = []
        self.ended: tuple[str, str] | None = None

    async def apply(self, command: WireModel) -> None:
        """Keep the command, or refuse one that needs a room."""
        if isinstance(command, RoomSend):
            raise PinecallError(NO_ROOM)
        self.applied.append(command)

    def hang_up(self, reason: str, by: str = "agent", *, at_once: bool = False) -> None:
        """End the call, once: the session ends it as the first reason said."""
        if self.ended is None:
            self.ended = (reason, by)


async def nothing_before(_call_id: str) -> None:
    return None


async def served_here(live: Live, store: Store, call: str, running: Written | None) -> list[Entry]:
    """The call served on `live`, its socket here collecting what it is sent; with no session, a worker's call."""
    sent: list[Entry] = []

    async def send(entry: Entry) -> None:
        sent.append(entry)

    live.sockets[APP] = send
    config = AgentConfig(slug=AGENT)
    log = Log(store, call, AGENT)
    served = Served(
        agent=AGENT,
        scope=Scope("org_1", Env.sandbox),
        app=APP,
        log=log,
        commands=asyncio.Queue(),
        context=context_of(call, Channel.web),
        config=config,
        tools=ToolCalls(config, log, nothing_before, nothing_before),
        running=None if running is None else cast(session.Session, running),
    )
    live.serve(served)
    await live.commands_heard(call)
    return sent


async def settled(sent: list[Entry], *, kind: str) -> Entry:
    """The first entry of the kind sent down the socket, waited for."""
    for _ in range(100):
        for entry in sent:
            if entry.type == kind:
                return entry
        await asyncio.sleep(0.01)
    raise AssertionError(f"no {kind} reached the socket: {[entry.type for entry in sent]}")


@needs_the_database
async def test_a_refused_command_is_answered_to_the_app_and_the_next_one_still_applies(store: Store, call: str) -> None:
    live = Live()
    running = Written()
    sent = await served_here(live, store, call, running)
    drawn = Command(
        type="room.send", agent=AGENT, call=call, id="kala:room.send", data={"topic": "kala.ui", "data": {}}
    )
    assert await send_command(live.signal, drawn)
    error = await settled(sent, kind="error")
    assert error.data["code"] == "refused" and error.data["message"] == NO_ROOM
    assert (error.data["command"], error.data["id"]) == ("room.send", "kala:room.send")
    # P F5 / T F2 / R F9: the app heard it, and the call's own log said nothing.
    said = [entry.data for entry in await store.whole(call) if entry.type == "error"]
    assert [(one["command"], one["message"]) for one in said] == [("room.send", NO_ROOM)]

    state = Command(type="state.set", agent=AGENT, call=call, id=None, data={"state": {"cart": []}})
    assert await send_command(live.signal, state)
    for _ in range(100):
        if running.applied:
            break
        await asyncio.sleep(0.01)
    assert [type(applied).__name__ for applied in running.applied] == ["StateSet"]
    live.close_call(call)


@needs_the_database
async def test_the_callers_hang_up_ends_a_written_call_the_gateway_runs_as_their_own(store: Store, call: str) -> None:
    """Said at the door on another gateway, the hang-up reaches the session here, once, as the caller's."""
    live = Live()
    running = Written()
    await served_here(live, store, call, running)
    said = Command(type=CALLER_HUNG_UP, agent=AGENT, call=call, id=None, data={})
    assert await send_command(live.signal, said)
    assert await send_command(live.signal, said)
    for _ in range(100):
        if running.ended is not None:
            break
        await asyncio.sleep(0.01)
    assert running.ended == ("caller_hung_up", "caller")
    assert running.applied == []
    live.close_call(call)


class Breaking(Written):
    """A written call's session that breaks on a room's command, with what no refusal of ours is."""

    @override
    async def apply(self, command: WireModel) -> None:
        """Raise what is not a PinecallError for a room's command, take the others."""
        if isinstance(command, RoomSend):
            raise RuntimeError("the session broke")
        await super().apply(command)


# A command the stream could not read, or the session broke on, ended the call's listener with an
# exception that nobody read: every command after it (a supervisor's end) was lost in silence.
@needs_the_database
async def test_a_command_the_stream_cannot_read_or_the_session_breaks_on_does_not_end_its_listener(
    store: Store, call: str
) -> None:
    live = Live()
    running = Breaking()
    await served_here(live, store, call, running)
    live.signal.publish(COMMANDS_CHANNEL.format(call=call), b"this is not a command")
    drawn = Command(type="room.send", agent=AGENT, call=call, id=None, data={"topic": "kala.ui", "data": {}})
    assert await send_command(live.signal, drawn)
    state = Command(type="state.set", agent=AGENT, call=call, id=None, data={"state": {"cart": []}})
    assert await send_command(live.signal, state)
    for _ in range(100):
        if running.applied:
            break
        await asyncio.sleep(0.01)
    assert [type(applied).__name__ for applied in running.applied] == ["StateSet"]
    live.close_call(call)


# Every gateway that serves a spoken call keeps its commands for the worker's stream, and a worker
# whose stream moved to a second gateway was sent again all the first had sent: an app's say, said twice.
@needs_the_database
async def test_a_spoken_calls_command_waits_on_every_gateway_under_the_one_id_it_was_sent_with(
    store: Store, call: str
) -> None:
    signal = LocalSignal()
    gateways = (Live(signal), Live(signal))
    for live in gateways:
        await served_here(live, store, call, None)
    said = Command(type="state.set", agent=AGENT, call=call, id="c1", data={"state": {"cart": []}})
    assert await send_command(signal, said) and await send_command(signal, said)
    waiting = [[await asyncio.wait_for(live.calls[call].commands.get(), 5.0) for _ in range(2)] for live in gateways]
    here, there = ([None if one is None else one.id for one in kept] for kept in waiting)
    assert here == there
    assert here[0] != here[1], "the id an app gives names the command to the app: two commands may carry one"
    assert [None if one is None else one.command for one in waiting[0]] == [said, said]
    for live in gateways:
        live.close_call(call)
