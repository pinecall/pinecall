"""A call's tool calls to its app, through its log: each asked once, awaited, and answered once."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from runtime.agents.declaration import DEFAULT_TOOL_TIMEOUT_S, Declaration
from runtime.calls.log import Filter, Log
from runtime.session import service as session
from runtime.wire.base import Entry
from runtime.wire.events import ToolCall
from runtime.wire.parts import ToolResult

# The `tool.result` a call's log holds for a tool call id, or None: what a finished call answered;
# and the `tool.call` it holds, or None: a call id asked already, maybe through another gateway.
type FindAnswer = Callable[[str], Awaitable[ToolResult | None]]
type FindCall = Callable[[str], Awaitable[Entry | None]]

# What a waiting round trip reads of the log: the answers, whichever gateway writes them.
RESULTS = Filter(types=frozenset({"tool.result"}))


@dataclass(frozen=True, slots=True)
class Awaited:
    """What a round trip waited out: the result, and whether the log already holds it."""

    result: ToolResult
    on_the_log: bool


# The log is the channel both ways: a tool.call reaches the app through whichever gateway holds its
# socket, and its tool.result is written there, once per call id; the gateway the worker asked
# waits for it on the log, and writes the timeout through the same guard.
class ToolCalls:
    """The app's tool calls of one call, each run once and awaited, and answered once finished."""

    def __init__(self, declaration: Declaration, log: Log, find_answer: FindAnswer, find_call: FindCall) -> None:
        """Nothing out yet."""
        self.declaration = declaration
        self.log = log
        self._find_answer = find_answer
        self._find_call = find_call
        self._waiting: dict[str, asyncio.Future[ToolResult]] = {}
        # One round trip per call id: a request retried joins the one running.
        self._trips: dict[str, asyncio.Future[ToolResult]] = {}

    async def run(self, use: session.ToolUse, speech: str | None) -> ToolResult:
        """Send the call to the app and return what it answered, once per call id."""
        trip = self._trips.get(use.call_id)
        if trip is None:
            trip = asyncio.ensure_future(self._round_trip(use, speech))
            self._trips[use.call_id] = trip
            trip.add_done_callback(lambda _: self._trips.pop(use.call_id, None))
        # Shielded: whoever started it may be cancelled while the app still answers.
        return await asyncio.shield(trip)

    def answer(self, result: ToolResult) -> bool:
        """Hand a result to the call waiting for it; False when nobody is."""
        waiting = self._waiting.pop(result.call_id, None)
        if waiting is None or waiting.done():
            return False
        waiting.set_result(result)
        return True

    # A call id the log already answered (a retry whose answer was lost, or asked of a gateway
    # that restarted) is answered from it and never sent to the app again: a tool may book or
    # charge. Looked up inside the round trip, so a retry that arrives meanwhile joins it. A retry
    # that reached this gateway after another asked the app: the stored tool.call is told again
    # (its gateway may have died before telling anyone) and waited on, never asked twice.
    async def _round_trip(self, use: session.ToolUse, speech: str | None) -> ToolResult:
        earlier = await self._find_answer(use.call_id)
        if earlier is not None:
            return earlier
        stored = await self._find_call(use.call_id)
        if stored is None:
            called = ToolCall(call_id=use.call_id, name=use.name, arguments=use.arguments, speech_id=speech)
            stored = await self.log.append("tool.call", called.dump())
        else:
            self.log.republish(stored)
        awaited = await self._await(use, stored)
        if awaited.on_the_log or await self.log.answer(awaited.result.dump()) is not None:
            return awaited.result
        # Another gateway answered first: its answer is the call's.
        return await self._find_answer(use.call_id) or awaited.result

    # The deadline runs from the tool.call, not from this request: a retry waits what is left. A
    # timeout is an error the model recovers from in the same turn; a cancellation propagates,
    # since the turn is gone and must not get a tool.result.
    async def _await(self, use: session.ToolUse, stored: Entry) -> Awaited:
        waiting: asyncio.Future[ToolResult] = asyncio.get_running_loop().create_future()
        self._waiting[use.call_id] = waiting
        spec = self.declaration.tools_by_name.get(use.name)
        timeout = spec.timeout_s if spec else DEFAULT_TOOL_TIMEOUT_S
        heard = asyncio.ensure_future(self._hear(use.call_id, stored.seq))
        left = max(timeout - (self.log.clock() - stored.ts), 0.0)
        try:
            done, _ = await asyncio.wait({waiting, heard}, timeout=left, return_when="FIRST_COMPLETED")
            if waiting in done:
                return Awaited(waiting.result(), on_the_log=False)
            if heard in done:
                return Awaited(heard.result(), on_the_log=True)
            lapsed = f"{use.name} did not answer within {timeout:g}s"
            return Awaited(ToolResult(call_id=use.call_id, name=use.name, error=lapsed), on_the_log=False)
        finally:
            self._waiting.pop(use.call_id, None)
            heard.cancel()

    async def _hear(self, call_id: str, after: int) -> ToolResult:
        async for entry in self.log.stream(after=after, only=RESULTS):
            if entry.type == "tool.result" and entry.data.get("call_id") == call_id:
                return ToolResult.model_validate((await self.log.privacy.open(entry)).data)
        # The call ended with no answer: the deadline answers.
        unanswered: asyncio.Future[ToolResult] = asyncio.get_running_loop().create_future()
        return await unanswered
