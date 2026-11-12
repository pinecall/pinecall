"""The calls a gateway serves: a refused command is answered, the stream goes on, a caller's hang-up ends the call."""

import asyncio
import dataclasses
import functools
import time

from runtime.actor import Scope
from runtime.enums import Channel, Env
from runtime.live.parts import LiveParts
from runtime.live.peers import COMMANDS
from runtime.live.served import Calls, Opening, Served
from runtime.live.service import commands, openings
from runtime.live.service.commands import CALLER_HUNG_UP
from runtime.session import service as session
from runtime.wire.base import Command, Entry
from runtime.wire.signal import Commanded
from tests.conftest import needs_the_database, until
from tests.live.sockets import an_app
from tests.session.conftest import AGENT, NOBODY, Box, a_session, context_of

pytestmark = needs_the_database

APP = "app_1"
SCOPE = Scope("org_1", Env.sandbox)
WITHIN_S = 5.0


async def served_here(live: LiveParts, call: str, *, written: bool) -> Served:
    """The call served by the gateway and bound to the app: a written one runs its session here, a worker's none."""
    opening = Opening(context_of(call, Channel.web), NOBODY, SCOPE, None, owner=APP)
    served = openings.serve(live, opening, opened_here=True)
    if written:
        running = a_session(Box(served.log), NOBODY)
        await running.start()
        live.calls.run(served, running)
    await live.calls.wait_until_heard(call)
    return served


def running_of(served: Served) -> session.Session:
    """The session the gateway runs for a written call."""
    assert served.running is not None
    return served.running


async def logged(live: LiveParts, call: str, kind: str) -> list[Entry]:
    """The call's entries of the kind, waited for until its log holds one."""
    deadline = time.monotonic() + WITHIN_S
    while True:
        found = [entry for entry in await live.store.whole_of(call) if entry.type == kind]
        if found:
            return found
        assert time.monotonic() < deadline, f"no {kind} was written to {call}"
        await asyncio.sleep(0.02)


# Said on the call's channel, as the gateway an app or a desk sent it to says it to the one that runs the call.
async def told(live: LiveParts, command: Command, sent_as: str = "c1") -> bool:
    """Tell the command to whichever gateway serves its call; whether one heard."""
    assert command.call is not None
    return await COMMANDS.reach(live.signal, Commanded(id=sent_as, command=command), call=command.call)


async def test_a_refused_command_is_answered_to_the_app_and_the_next_one_still_applies(
    live: LiveParts, call: str
) -> None:
    app = an_app(live, APP, SCOPE)
    served = await served_here(live, call, written=True)
    drawn = Command(
        type="room.send", agent=AGENT, call=call, id="kala:room.send", data={"topic": "kala.ui", "data": {}}
    )
    assert await told(live, drawn)
    await until(lambda: bool(app.of("error")), WITHIN_S)
    # P F5 / T F2 / R F9: the app heard it, and the call's own log says it too. The app is told as the
    # command is refused and sent the log's entry by the call's pump: one refusal, whichever it reads.
    (said,) = [entry.data for entry in await live.store.whole_of(call) if entry.type == "error"]
    assert said["code"] == "refused" and "this call is written" in said["message"]
    assert (said["command"], said["id"]) == ("room.send", "kala:room.send")
    assert all(heard.data == said for heard in app.of("error"))

    state = Command(type="state.set", agent=AGENT, call=call, id=None, data={"state": {"cart": []}})
    assert await told(live, state)
    (applied,) = await logged(live, call, "state.changed")
    assert applied.data["state"] == {"cart": []}
    await running_of(served).end("caller_hung_up", "caller")
    live.calls.close_call(call)


async def test_the_callers_hang_up_ends_a_written_call_the_gateway_runs_as_their_own(
    live: LiveParts, call: str
) -> None:
    """Said to another gateway, the hang-up reaches the session here, once, as the caller's."""
    an_app(live, APP, SCOPE)
    served = await served_here(live, call, written=True)
    said = Command(type=CALLER_HUNG_UP, agent=AGENT, call=call, id=None, data={})
    assert await told(live, said)
    assert await told(live, said)
    # Over, not only closing: its close writes the call's last entries, and the test's gateway goes with it.
    await asyncio.wait_for(running_of(served).over.wait(), WITHIN_S)
    ended = [entry.data for entry in await live.store.whole_of(call) if entry.type == "call.ended"]
    assert [(one["reason"], one["ended_by"]) for one in ended] == [("caller_hung_up", "caller")]
    live.calls.close_call(call)


# A command the stream could not read, or the session refused, ended the call's listener with an
# exception that nobody read: every command after it (a supervisor's end) was lost in silence.
async def test_a_command_the_stream_cannot_read_does_not_end_its_listener(live: LiveParts, call: str) -> None:
    an_app(live, APP, SCOPE)
    served = await served_here(live, call, written=True)
    live.signal.publish(COMMANDS.name.format(call=call), b"this is not a command")
    state = Command(type="state.set", agent=AGENT, call=call, id=None, data={"state": {"cart": []}})
    assert await told(live, state)
    (applied,) = await logged(live, call, "state.changed")
    assert applied.data["state"] == {"cart": []}
    await running_of(served).end("caller_hung_up", "caller")
    live.calls.close_call(call)


# Every gateway that serves a spoken call keeps its commands for the worker's stream, and a worker
# whose stream moved to a second gateway was sent again all the first had sent: an app's say, said twice.
async def test_a_spoken_calls_command_waits_on_every_gateway_under_the_one_id_it_was_sent_with(
    live: LiveParts, call: str
) -> None:
    an_app(live, APP, SCOPE)
    # A second gateway of the box: calls of its own, heard on the same signal.
    its_calls = Calls(live.signal, live.sockets, live.owners, functools.partial(commands.hear, live.sockets))
    await its_calls.start()
    other = dataclasses.replace(live, calls=its_calls)
    try:
        here = await served_here(live, call, written=False)
        there = await served_here(other, call, written=False)
        said = Command(type="state.set", agent=AGENT, call=call, id="c1", data={"state": {"cart": []}})
        assert await told(live, said, "first") and await told(live, said, "second")
        waiting = [
            [await asyncio.wait_for(served.commands.get(), WITHIN_S) for _ in range(2)] for served in (here, there)
        ]
        ids_here, ids_there = ([None if one is None else one.id for one in kept] for kept in waiting)
        assert ids_here == ids_there == ["first", "second"]
        assert [None if one is None else one.command for one in waiting[0]] == [said, said]
    finally:
        its_calls.close_call(call)
        await its_calls.close()
        live.calls.close_call(call)
