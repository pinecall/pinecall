"""The app's tool calls of one call: each run once, answered once, and read back off the log by whoever asks again."""

import asyncio
import contextlib

from runtime.actor import Scope
from runtime.agents.declaration import Declaration, ToolSpec
from runtime.calls import folds
from runtime.calls.log.log import Log
from runtime.enums import Channel, Env
from runtime.live.parts import LiveParts
from runtime.live.served import Opening, Served
from runtime.live.service import openings
from runtime.session.call import ToolUse
from runtime.wire.base import Entry
from runtime.wire.events import ToolResult
from tests.conftest import needs_the_database
from tests.session.conftest import AGENT, context_of

pytestmark = needs_the_database

SCOPE = Scope("org_1", Env.sandbox)
BOOK = ToolSpec("book", "Book a table.", {"type": "object", "properties": {}}, timeout_s=0.1)
SLOW = ToolSpec("book", "Book.", {"type": "object"}, timeout_s=5)


def served_on(live: LiveParts, call: str, tool: ToolSpec, *, opened_here: bool = True) -> Served:
    """The call as the gateway serves it, its agent declaring the tool: its tool calls are the gateway's own."""
    opening = Opening(context_of(call, Channel.web), Declaration(slug=AGENT, tools=(tool,)), SCOPE, None)
    return openings.serve(live, opening, opened_here=opened_here)


# The tap runs inside the append; the round trip then waits for its answer before this wakes.
def went_out(log: Log, many: int = 1) -> asyncio.Event:
    """Set once this many tool calls went out to the app and wait for their answers."""
    out = asyncio.Event()
    sent: list[Entry] = []

    async def tap(entry: Entry) -> None:
        if entry.type == "tool.call":
            sent.append(entry)
        if len(sent) >= many:
            out.set()

    log.tap(tap)
    return out


async def test_a_tool_asked_twice_by_call_id_is_written_once_and_answered_once(live: LiveParts, call: str) -> None:
    served = served_on(live, call, BOOK)
    use = ToolUse("t1", "book", {"day": "lunes"})
    out = went_out(served.log)
    first = asyncio.create_task(served.tools.run(use, "speech_1"))
    second = asyncio.create_task(served.tools.run(use, "speech_1"))
    await asyncio.wait_for(out.wait(), 5)
    assert served.tools.answer(ToolResult(call_id="t1", name="book", output="ok"))
    assert await first == await second
    written = [entry.type for entry in await live.store.whole_of(call)]
    assert written == ["tool.call", "tool.result"]
    live.calls.close_call(call)


# The answer was lost, or the gateway restarted: the log holds the result, and the app is not
# asked again, since a tool may book or charge.
async def test_a_tool_asked_again_after_it_finished_is_answered_from_the_log_and_never_run_twice(
    two_gateways: tuple[LiveParts, LiveParts], call: str
) -> None:
    live, another = two_gateways
    served = served_on(live, call, BOOK)
    use = ToolUse("t1", "book", {"day": "lunes"})
    out = went_out(served.log)
    first = asyncio.create_task(served.tools.run(use, "speech_1"))
    await asyncio.wait_for(out.wait(), 5)
    assert served.tools.answer(ToolResult(call_id="t1", name="book", output="booked"))
    assert (await first).output == "booked"
    again = await served.tools.run(use, "speech_1")
    # Asked of a gateway that never ran it: the same answer, read off the call's log.
    elsewhere = served_on(another, call, BOOK, opened_here=False)
    from_another_gateway = await elsewhere.tools.run(use, "speech_1")
    assert again == from_another_gateway == await first
    assert not served.tools.answer(ToolResult(call_id="t1", name="book", output="twice")), "nobody waits for it"
    assert [entry.type for entry in await live.store.whole_of(call)] == ["tool.call", "tool.result"]
    live.calls.close_call(call)
    another.calls.close_call(call)


# What a socket that takes the call is sent after call.attached: the tools still waiting, off the log.
async def test_the_tools_still_waiting_are_the_entries_that_went_out_in_order(live: LiveParts, call: str) -> None:
    served = served_on(live, call, SLOW)
    first, both = went_out(served.log, 1), went_out(served.log, 2)
    running = [asyncio.create_task(served.tools.run(ToolUse("t1", "book", {}), None))]
    await asyncio.wait_for(first.wait(), 5)
    running.append(asyncio.create_task(served.tools.run(ToolUse("t2", "book", {}), None)))
    await asyncio.wait_for(both.wait(), 5)
    waiting = folds.list_unanswered_tools(await live.store.whole_of(call))
    assert [entry.data["call_id"] for entry in waiting] == ["t1", "t2"]
    for call_id in ("t1", "t2"):
        assert served.tools.answer(ToolResult(call_id=call_id, name="book", output="ok"))
    await asyncio.gather(*running)
    assert folds.list_unanswered_tools(await live.store.whole_of(call)) == []
    live.calls.close_call(call)


async def test_a_tool_that_does_not_answer_in_time_is_an_error_the_model_recovers_from(
    live: LiveParts, call: str
) -> None:
    served = served_on(live, call, BOOK)
    result = await served.tools.run(ToolUse("t1", "book", {}), None)
    assert result.error == "book did not answer within 0.1s"
    answered = [entry.data for entry in await live.store.whole_of(call) if entry.type == "tool.result"]
    assert [one["error"] for one in answered] == ["book did not answer within 0.1s"]
    assert not served.tools.answer(ToolResult(call_id="t1", name="book", output="late")), "nobody waits any more"
    live.calls.close_call(call)


# Whoever asked may be cancelled while the app still answers (a request that timed out, a turn the
# caller cut): the round trip goes on, and the answer is the call's when it comes.
async def test_a_tool_whose_asker_went_away_is_still_answered_on_the_log(live: LiveParts, call: str) -> None:
    served = served_on(live, call, SLOW)
    out = went_out(served.log)
    asking = asyncio.create_task(served.tools.run(ToolUse("t1", "book", {}), None))
    await asyncio.wait_for(out.wait(), 5)
    asking.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await asking
    assert served.tools.answer(ToolResult(call_id="t1", name="book", output="ok"))
    again = await served.tools.run(ToolUse("t1", "book", {}), None)
    assert again.output == "ok"
    assert [entry.type for entry in await live.store.whole_of(call)] == ["tool.call", "tool.result"]
    live.calls.close_call(call)
