"""A call's tool calls to its app, through its log: each asked once, awaited, and answered once."""

import asyncio
from collections.abc import Awaitable, Callable

from pinecall_runtime.agents.declaration import DEFAULT_TOOL_TIMEOUT_S, AgentConfig
from pinecall_runtime.calls.fanout import Filter
from pinecall_runtime.calls.logs import Log
from pinecall_runtime.session import service as session
from pinecall_runtime.wire.base import Entry
from pinecall_runtime.wire.events import ToolCall
from pinecall_runtime.wire.parts import ToolResult

# The `tool.result` a call's log holds for a tool call id, or None: what a finished call answered;
# and the `tool.call` it holds, or None: a call id asked already, maybe through another gateway.
type Answered = Callable[[str], Awaitable[ToolResult | None]]
type Called = Callable[[str], Awaitable[Entry | None]]

# What a waiting round trip reads of the log: the answers, whichever gateway writes them.
RESULTS = Filter(types=frozenset({"tool.result"}))


# The log is the channel both ways: a tool.call reaches the app through whichever gateway holds its
# socket, and its tool.result is written there, once per call id; the gateway the worker asked
# waits for it on the log, and writes the timeout through the same guard.
class ToolCalls:
    """The app's tool calls of one call, each run once and awaited, and answered once finished."""

    def __init__(self, config: AgentConfig, log: Log, answered_before: Answered, called_before: Called) -> None:
        """Nothing out yet."""
        self.config = config
        self.log = log
        self.answered_before = answered_before
        self.called_before = called_before
        self.waiting: dict[str, asyncio.Future[ToolResult]] = {}
        # One round trip per call id: a request retried joins the one running.
        self.running: dict[str, asyncio.Future[ToolResult]] = {}
        # Unanswered tool.call entries, sent again to a socket that takes the call over.
        self.sent: dict[str, Entry] = {}

    async def run(self, use: session.ToolUse, speech: str | None) -> ToolResult:
        """Send the call to the app and return what it answered, once per call id."""
        running = self.running.get(use.call_id)
        if running is None:
            running = asyncio.ensure_future(self._round_trip(use, speech))
            self.running[use.call_id] = running
            running.add_done_callback(lambda _: self.running.pop(use.call_id, None))
        # Shielded: whoever started it may be cancelled while the app still answers.
        return await asyncio.shield(running)

    def pending(self) -> list[Entry]:
        """The tool.call entries nobody answered, in the order they went out."""
        return sorted(self.sent.values(), key=lambda entry: entry.seq)

    def answer(self, result: ToolResult) -> bool:
        """Hand a result to the call waiting for it; False when nobody is."""
        waiting = self.waiting.pop(result.call_id, None)
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
        earlier = await self.answered_before(use.call_id)
        if earlier is not None:
            return earlier
        stored = await self.called_before(use.call_id)
        if stored is None:
            called = ToolCall(call_id=use.call_id, name=use.name, arguments=use.arguments, speech_id=speech)
            stored = await self.log.append("tool.call", called.dump())
        else:
            self.log.republish(stored)
        self.sent[use.call_id] = stored
        try:
            result, on_the_log = await self._awaited(use, stored)
        finally:
            self.sent.pop(use.call_id, None)
        if on_the_log or await self.log.answer(result.dump()) is not None:
            return result
        # Another gateway answered first: its answer is the call's.
        return await self.answered_before(use.call_id) or result

    # The deadline runs from the tool.call, not from this request: a retry waits what is left. A
    # timeout is an error the model recovers from in the same turn; a cancellation propagates,
    # since the turn is gone and must not get a tool.result.
    async def _awaited(self, use: session.ToolUse, stored: Entry) -> tuple[ToolResult, bool]:
        waiting: asyncio.Future[ToolResult] = asyncio.get_running_loop().create_future()
        self.waiting[use.call_id] = waiting
        declared_as = self.config.tools_by_name.get(use.name)
        timeout = declared_as.timeout_s if declared_as else DEFAULT_TOOL_TIMEOUT_S
        heard = asyncio.ensure_future(self._heard(use.call_id, stored.seq))
        left = max(timeout - (self.log.clock() - stored.ts), 0.0)
        try:
            done, _ = await asyncio.wait({waiting, heard}, timeout=left, return_when="FIRST_COMPLETED")
            if waiting in done:
                return waiting.result(), False
            if heard in done:
                return heard.result(), True
            lapsed = f"{use.name} did not answer within {timeout:g}s"
            return ToolResult(call_id=use.call_id, name=use.name, error=lapsed), False
        finally:
            self.waiting.pop(use.call_id, None)
            heard.cancel()

    async def _heard(self, call_id: str, after: int) -> ToolResult:
        async for entry in self.log.stream(after=after, only=RESULTS):
            if entry.type == "tool.result" and entry.data.get("call_id") == call_id:
                return ToolResult.model_validate(entry.data)
        # The call ended with no answer: the deadline answers.
        unanswered: asyncio.Future[ToolResult] = asyncio.get_running_loop().create_future()
        return await unanswered
