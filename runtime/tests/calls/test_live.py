"""The calls a gateway serves: a command from another gateway refused is answered, and the stream goes on."""

import asyncio
from typing import cast

from pinecall_runtime.agents.declaration import AgentConfig
from pinecall_runtime.calls.logs import Log
from pinecall_runtime.calls.service.live import Live, Served
from pinecall_runtime.calls.service.peers import send_command
from pinecall_runtime.calls.service.tool_calls import ToolCalls
from pinecall_runtime.calls.store import Store
from pinecall_runtime.enums import Channel, Env
from pinecall_runtime.exceptions import PinecallError
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.session import service as session
from pinecall_runtime.wire.base import Command, Entry, WireModel
from pinecall_runtime.wire.commands import RoomSend
from tests.conftest import needs_the_database
from tests.session.conftest import AGENT, context_of

APP = "app_1"
NO_ROOM = "RoomSend is not something this call does"


class Written:
    """A written call's session as the stream sees it: it takes every command but a room's."""

    def __init__(self) -> None:
        """Nothing applied yet."""
        self.applied: list[WireModel] = []

    async def apply(self, command: WireModel) -> None:
        """Keep the command, or refuse one that needs a room."""
        if isinstance(command, RoomSend):
            raise PinecallError(NO_ROOM)
        self.applied.append(command)


async def nothing_before(_call_id: str) -> None:
    return None


async def served_here(live: Live, store: Store, call: str, running: Written) -> list[Entry]:
    """The call served on `live`, its socket here collecting what it is sent."""
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
        running=cast(session.Session, running),
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

    state = Command(type="state.set", agent=AGENT, call=call, id=None, data={"state": {"cart": []}})
    assert await send_command(live.signal, state)
    for _ in range(100):
        if running.applied:
            break
        await asyncio.sleep(0.01)
    assert [type(applied).__name__ for applied in running.applied] == ["StateSet"]
    live.close_call(call)
