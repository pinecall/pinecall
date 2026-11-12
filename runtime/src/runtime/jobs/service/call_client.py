"""A call open at the gateway, as its worker reaches it: its log, its tools, its lookups, its commands, its seal."""

import base64
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from functools import partial
from pathlib import Path

from runtime.actor import Scope
from runtime.agents.declaration import Declaration
from runtime.exceptions import Conflict, UpstreamError
from runtime.jobs.service.client import LONGEST_WAIT_S, TIMEOUT_S, GatewayClient, scope_params
from runtime.jobs.service.entries import EntriesStream
from runtime.jobs.service.measures import report_batch
from runtime.kit.loops import survive
from runtime.kit.retry import keep_asking
from runtime.kit.text import Json, JsonObject, a_list, a_mapping
from runtime.session import service as session
from runtime.telephony import service as telephony
from runtime.wire.base import BatchedEntry, Command, Entry
from runtime.wire.events import ToolCall
from runtime.wire.metrics import ModelUsage
from runtime.wire.parts import PlatformTool, ToolResult
from runtime.wire.worker import (
    LegTrunk,
    LegTrunkResponse,
    LookupResponse,
    OpenCallRequest,
    OpenCallResponse,
    RecordingKeyResponse,
    SealCallRequest,
)

# A caller is waiting on the line while the open is asked again.
OPENED_WITHIN_S = 15.0
# One request waits all of it: a seal writes memory and asks the judges, which outlast TIMEOUT_S.
# What does not seal within it the gateway's reaper seals.
A_SEAL_S = 30.0
# A tool whose declaration names no wait.
A_TOOL_S = 30.0

ALREADY_OVER = 409
NOT_SERVED = 404

# The call's recording kept as the seal names it; None when the call has none.
type KeepRecording = Callable[[], Awaitable[str | None]]


# The session's `Platform`, in a worker: every method is one of the gateway's endpoints on the call.
# What the call's job adds is told here once: where a batch's measures go, the vendors that ran on
# the box's key, and how its recording is kept before the seal names it.
class CallClient:
    """One call open at the gateway: what its worker writes to it, asks of it, hears from it and ends it with."""

    def __init__(
        self,
        gateway: GatewayClient,
        call: str,
        opening: OpenCallRequest | None = None,
        opened: OpenCallResponse | None = None,
        declaration: Declaration | None = None,
    ) -> None:
        """A call this worker opened, or (with no opening) one it took over from a worker that went away."""
        self.gateway = gateway
        self.call = call
        # What it was opened with, said again to a gateway that restarted.
        self.opening = opening
        self.opened = opened
        self.declaration = declaration
        self.entries = EntriesStream(*gateway.socket_at(f"/v1/calls/{call}/entries"))
        # The ids of the commands the call was handed: one a gateway sends again is dropped.
        self.heard: set[str] = set()
        self.measures: Path | None = None
        self.lent: list[str] = []
        self.keep_recording: KeepRecording | None = None

    @property
    def scope(self) -> Scope:
        """The org, the env and the holder the call runs for."""
        context = self._opening().context
        return Scope(context.route.org, context.route.env, context.holder or "")

    # ── the session's platform ──

    # Retried without a limit, the same batch after the same count: the log answers a batch it
    # already took with the seqs it gave it, so an answer lost never writes an entry twice.
    async def append_many(self, entries: list[BatchedEntry], *, after: int) -> list[Entry]:
        """Write a batch of the call's entries once, in order; the gateway numbers them."""
        if self.measures is not None:
            report_batch(self.measures, entries)
        return await self._ask_again(lambda: self._append(entries, after), None, "its entries")

    # The gateway answers a lapsed tool at its own deadline: wait past it, so the model reads
    # that answer and not a timeout of ours. Idempotent per call id, so a retry joins.
    async def run_tool(self, use: session.ToolUse, speech: str | None) -> ToolResult:
        """Run a tool in the app that declared it and return what it answered."""
        spec = None if self.declaration is None else self.declaration.tools_by_name.get(use.name)
        waiting = (A_TOOL_S if spec is None else spec.timeout_s) + TIMEOUT_S
        called = ToolCall(call_id=use.call_id, name=use.name, arguments=use.arguments, speech_id=speech)
        path = f"/v1/calls/{self.call}/tools?agent={self._opening().agent}"
        answer = await self._ask_again(lambda: self._on_the_call("POST", path, called.dump(), waiting), waiting, path)
        return ToolResult.model_validate(answer)

    async def look_up(self, tool: PlatformTool, arguments: JsonObject, speech: str | None) -> JsonObject:
        """Recall or search, run by the gateway, which writes what it found on the log."""
        asked: Json = {"tool": tool, "input": dict(arguments), "speech_id": speech}
        answer = await self._on_the_call("POST", f"/v1/calls/{self.call}/lookup", asked)
        return LookupResponse.model_validate(answer).output

    # Sealed already is this seal, whose answer a gateway that died took with it.
    async def seal(self, usage: list[ModelUsage], outcome: str) -> None:
        """Hand the end of the call to the gateway, which prices, judges and seals it."""
        recording = None if self.keep_recording is None else await self.keep_recording()
        sealing = SealCallRequest(usage=usage, outcome=outcome, recording=recording, lent=list(self.lent))
        path = f"/v1/calls/{self.call}/sealed"
        try:
            await self._ask_again(lambda: self._on_the_call("POST", path, sealing.dump(), A_SEAL_S), A_SEAL_S, path)
        except UpstreamError as refused:
            if refused.answered != ALREADY_OVER:
                raise
        await self.entries.close()

    # A call sealed already has nothing waiting for it: the same answer a seal asked twice gets.
    async def release_seal(self) -> None:
        """Say the app's end hook ran and what it wrote was sent; the gateway's seal waits for it."""
        try:
            await self._on_the_call("POST", f"/v1/calls/{self.call}/done")
        except UpstreamError as refused:
            if refused.answered != ALREADY_OVER:
                raise

    # ── the call's room ──

    # The gateway judges the leg (shape and pace) and names the trunk; a refusal is its sentence.
    async def leg(self, to: str, shown: str | None) -> LegTrunk:
        """How to dial a leg of the call: the trunk inline and the number shown."""
        asked = scope_params(self.scope) | {"to": to, "call": self.call} | ({"from": shown} if shown else {})
        path = f"/v1/agents/{self._opening().agent}/outbound-trunk"
        return LegTrunkResponse.model_validate(await self.gateway.read("GET", path, params=asked)).trunk

    # A cold transfer dials nothing of ours, so no trunk: the gateway judges the leg alone.
    async def send_on(self, to: str) -> None:
        """Have the gateway judge a cold transfer's leg; its refusal is its sentence."""
        asked = scope_params(self.scope) | {"to": to, "call": self.call}
        await self.gateway.read("POST", f"/v1/agents/{self._opening().agent}/cold-transfer", params=asked)

    # Asked each time a verb of the room dials: never cached, so a refusal carries the guards' reason.
    async def trunk(self, to: str) -> telephony.Trunk:
        """How the call's room dials a second leg: the trunk inline, the org's number shown."""
        leg = await self.leg(to, self._opening().context.route.number)
        return telephony.Trunk(config=telephony.sip_config(leg), shown=leg.shown)

    # A code nobody issued is an ordinary answer: the caller may be dialling an extension.
    async def claim(self, code: str) -> None:
        """Tie the call to the page showing the code; a code no page waits on is no failure."""
        try:
            await self._on_the_call("POST", f"/v1/calls/{self.call}/claim", {"code": code})
        except UpstreamError as refused:
            if refused.answered != NOT_SERVED:
                raise

    # Made once for the call, and the same when asked again.
    async def recording_key(self) -> bytes:
        """The key the call's recording is sealed under before it is kept."""
        answer = await self._on_the_call("POST", f"/v1/calls/{self.call}/recording/key")
        return base64.urlsafe_b64decode(RecordingKeyResponse.model_validate(answer).key)

    # ── the call's log, read back ──

    async def state(self) -> tuple[JsonObject, int]:
        """The call's state as the gateway folds it, and the seq it was folded to."""
        answer: object = await self._on_the_call("GET", f"/v1/calls/{self.call}/state")
        read = dict(answer) if a_mapping(answer) else {}
        folded = read.get("state")
        return (dict(folded) if a_mapping(folded) else {}), int(str(read.get("last_seq") or 0))

    async def since(self, after: int) -> AsyncIterator[Entry]:
        """The stored entries above the cursor, page by page, until the log's end."""
        cursor: int | None = after
        while cursor is not None:
            path = f"/v1/calls/{self.call}/events?after={cursor}"
            page: object = await self._ask_again(partial(self.gateway.read, "GET", path), A_SEAL_S, path)
            read = dict(page) if a_mapping(page) else {}
            entries = read.get("entries")
            listed: list[object] = list(entries) if a_list(entries) else []
            for entry in listed:
                yield Entry.model_validate(entry)
            further = read.get("next")
            cursor = further if isinstance(further, int) else None

    async def tail(self, after: int) -> AsyncIterator[Entry]:
        """The entries above the cursor, then the live ones, until the call ends."""
        async for sent in self.gateway.stream(f"/v1/calls/{self.call}/events?after={after}"):
            yield Entry.model_validate(sent.data)

    # A stream that ends is the gateway that went away or the call that was sealed; a 404 is a
    # gateway that forgot the call, told it again once. Whoever follows the call opens the stream again.
    async def commands(self) -> AsyncIterator[Command]:
        """The app's commands for the call, each once, in the order it sent them, until the stream ends."""
        try:
            async for command in self._hear():
                yield command
        except UpstreamError as refused:
            if not await self._reopen(refused):
                raise
        else:
            return
        async for command in self._hear():
            yield command

    async def aclose(self) -> None:
        """Close the call's socket; the gateway's pool is not this call's to close."""
        await self.entries.close()

    # ── private ──

    def _opening(self) -> OpenCallRequest:
        if self.opening is None:
            raise Conflict(
                f"call {self.call} was opened by another worker: this one writes to it and seals it, nothing else"
            )
        return self.opening

    async def _ask_again[T](self, ask: Callable[[], Awaitable[T]], within_s: float | None, what: str) -> T:
        return await keep_asking(ask, within_s=within_s, what=f"call {self.call}, {what}", longest_s=LONGEST_WAIT_S)

    async def _append(self, entries: Sequence[BatchedEntry], after: int) -> list[Entry]:
        try:
            return await self.entries.append_many(entries, after=after)
        except UpstreamError as refused:
            if not await self._reopen(refused):
                raise
        return await self.entries.append_many(entries, after=after)

    # A 404 for a call this worker opened is a gateway that restarted: say the call again, once.
    async def _on_the_call(self, method: str, path: str, data: Json = None, wait_s: float | None = None) -> Json:
        try:
            return await self.gateway.read(method, path, data, wait_s=wait_s)
        except UpstreamError as refused:
            if not await self._reopen(refused):
                raise
        return await self.gateway.read(method, path, data, wait_s=wait_s)

    async def _reopen(self, refused: UpstreamError) -> bool:
        if refused.answered != NOT_SERVED or self.opening is None:
            return False
        await self.gateway.read("POST", f"/v1/calls/{self.call}/reopened", self.opening.dump())
        return True

    # Every gateway that serves the call keeps its commands for this stream: one that takes the
    # stream after another sends again what the first sent, under the same ids.
    async def _hear(self) -> AsyncIterator[Command]:
        async for sent in self.gateway.stream(f"/v1/calls/{self.call}/commands"):
            if sent.id is not None and sent.id in self.heard:
                continue
            if sent.id is not None:
                self.heard.add(sent.id)
            if (command := _command_of(sent.data, self.call)) is not None:
                yield command


# Asked again while the gateway is away: an open is the same call by its id (one claim, one
# opening, one ringing), so an answer lost with a gateway that died is not a call lost.
async def open_call(
    gateway: GatewayClient, opening: OpenCallRequest, declaration: Declaration | None = None
) -> CallClient:
    """Open the call's log at the gateway; the call open, with what the org's minutes leave it."""
    answer = await keep_asking(
        lambda: gateway.read("POST", "/v1/calls", opening.dump()),
        within_s=OPENED_WITHIN_S,
        what=f"opening call {opening.context.call}",
        longest_s=LONGEST_WAIT_S,
    )
    return CallClient(gateway, opening.context.call, opening, OpenCallResponse.model_validate(answer), declaration)


# A frame this worker cannot read (a gateway newer than it) is said and skipped: the stream goes on.
def _command_of(frame: Mapping[str, object], call: str) -> Command | None:
    command: Command | None = None
    with survive("reading a command of the app", call):
        command = Command.model_validate(frame)
    return command
