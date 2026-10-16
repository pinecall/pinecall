"""One live call as the app holds it: what the log taught it, and the commands it sends."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal

from pinecall._listeners import AnyListener, Listener, Listeners
from pinecall.wire._names import Channel, JsonObject, Medium
from pinecall.wire.commands import (
    AgentReply,
    AgentSay,
    CallClaim,
    CallEvent,
    CallHangup,
    CallLog,
    PromptSet,
    StateSet,
    ToolsSet,
)
from pinecall.wire.events_call import (
    CallAttached,
    CallClaimed,
    CallDialing,
    CallRinging,
    CallStarted,
)
from pinecall.wire.events_turn import StateChanged
from pinecall.wire.frames import WireModel
from pinecall.wire.parts import Contact, ToolResult, ToolSpec

CallStatus = Literal["ringing", "dialing", "active", "ended"]

# How a call sends a command: its type, the call's id, and the command's data.
Send = Callable[[str, str | None, WireModel], None]


def day_of(ts: float) -> str:
    """`YYYY-MM-DD` of a moment, in this process's own timezone."""
    return datetime.fromtimestamp(ts, UTC).astimezone().date().isoformat()


def interruptible(*, allow: bool | None) -> dict[str, bool]:
    """`allow_interruptions` when it was said; absent, the world's default holds."""
    return {} if allow is None else {"allow_interruptions": allow}


class Call:
    """A call the app is serving. Its fields come from the log; each method sends one command."""

    def __init__(
        self, id_: str, send: Send, opened_at: float, on_error: Callable[[Exception], None]
    ) -> None:
        """A call first seen at `opened_at`, sending through `send`."""
        self.id = id_
        self._send = send
        self.status: CallStatus = "ringing"
        self.channel: Channel | None = None
        self.medium: Medium | None = None
        """Spoken or written, as `call.started` says; None before it."""
        self.from_: str | None = None
        self.to: str | None = None
        self.contact: Contact | None = None
        self.run: str | None = None
        """The eval run that opened the call, or None for a real caller."""
        self.claimed: str | None = None
        """The page's code this call claimed, or None."""
        self.state: JsonObject = {}
        """The app's state as last set here or said by `state.changed`."""
        self.today = day_of(opened_at)
        """The day the call opened; on `call.attached`, the day it first did."""
        self._listeners: Listeners[Call] = Listeners(on_error)

    def on(self, type_: str, listener: Listener["Call"]) -> Callable[[], None]:
        """Listen for one type of event on this call; the answer stops it."""
        return self._listeners.on(type_, listener)

    def on_any(self, listener: AnyListener["Call"]) -> Callable[[], None]:
        """Listen for every event on this call; the answer stops it."""
        return self._listeners.on_any(listener)

    # ── the commands ──

    def say(self, text: str, *, allow_interruptions: bool | None = None) -> None:
        """Say this, verbatim, now; it lands as `turn.agent`."""
        said = {"text": text} | interruptible(allow=allow_interruptions)
        self._send("agent.say", self.id, AgentSay.model_validate(said))

    def reply(self, instructions: str, *, allow_interruptions: bool | None = None) -> None:
        """Make the model speak now, following words the caller never hears."""
        asked = {"instructions": instructions} | interruptible(allow=allow_interruptions)
        self._send("agent.reply", self.id, AgentReply.model_validate(asked))

    def set_prompt(self, name: str, text: str) -> None:
        """Rewrite one named block of the prompt."""
        self._send("prompt.set", self.id, PromptSet(name=name, text=text))

    def set_tools(self, tools: list[ToolSpec]) -> None:
        """The tools the model may see now."""
        self._send("tools.set", self.id, ToolsSet(tools=tools))

    def set_state(self, state: JsonObject, changed: list[str] | None = None) -> None:
        """Send the whole state; it lands as `state.changed`."""
        self.state = dict(state)
        data = StateSet(state=state) if changed is None else StateSet(state=state, changed=changed)
        self._send("state.set", self.id, data)

    def tool_result(self, result: ToolResult) -> None:
        """Answer the model's tool call named by `result.call_id`."""
        self._send("tool.result", self.id, result)

    def event(self, name: str, data: JsonObject) -> None:
        """Hand the agent a fact from your backend; refused unless the agent accepts the name."""
        self._send("call.event", self.id, CallEvent(name=name, data=data))

    def hangup(self, reason: str | None = None) -> None:
        """End the call from the app's side."""
        self._send(
            "call.hangup", self.id, CallHangup() if reason is None else CallHangup(reason=reason)
        )

    def claim(self, code: str) -> None:
        """Bind the call to the page showing this four-digit code."""
        self._send("call.claim", self.id, CallClaim(code=code))

    def log(self, name: str, data: JsonObject | None = None) -> None:
        """Write a line of the app's own into the call's log; it lands as `custom`."""
        self._send("call.log", self.id, CallLog(name=name, data=data or {}))

    # ── what the log teaches it ──

    def take(self, type_: str, event: WireModel) -> None:
        """Learn what the event says of the call, then hand it to the call's listeners."""
        self._learn(event)
        if type_ == "call.ended":
            self.status = "ended"
        self._listeners.emit(type_, event, self)

    def _learn(self, event: WireModel) -> None:
        if isinstance(event, CallRinging):
            self.status = "ringing"
            self._line(event)
        elif isinstance(event, CallDialing):
            self.status = "dialing"
            self._line(event)
        elif isinstance(event, CallStarted):
            self.status = "active"
            self._line(event)
            self.medium = event.medium
            if event.today is not None:
                self.today = event.today
        elif isinstance(event, CallAttached):
            self.status = "active"
            self._line(event.started)
            self.medium = event.started.medium
            self.state = dict(event.state)
            self.today = event.started.today or day_of(event.started.started_at)
            self.claimed = event.claimed
        elif isinstance(event, StateChanged):
            self.state = dict(event.state)
        elif isinstance(event, CallClaimed):
            self.claimed = event.code

    def _line(self, line: CallRinging | CallDialing | CallStarted) -> None:
        self.channel = line.channel
        self.from_ = line.from_
        self.to = line.to
        self.contact = line.caller
        self.run = line.run


class CallBook:
    """The calls an agent is serving, by id; one is dropped once it ends."""

    def __init__(self, send: Send, on_error: Callable[[Exception], None]) -> None:
        """Calls opened here send through `send`."""
        self._send = send
        self._on_error = on_error
        self._live: dict[str, Call] = {}

    @property
    def live(self) -> list[Call]:
        """The calls in progress, in the order they opened."""
        return list(self._live.values())

    def of(self, id_: str, at: float) -> Call:
        """The call with this id, opened on first sight."""
        known = self._live.get(id_)
        if known is None:
            known = self._live[id_] = Call(id_, self._send, at, self._on_error)
        return known

    def forget(self, call: Call) -> None:
        """Drop the call once it has ended."""
        if call.status == "ended":
            self._live.pop(call.id, None)
