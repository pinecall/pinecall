"""What a call is while it runs, spoken or written: its state, what the app's commands write, what it reaches."""

import contextlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Protocol

from livekit.agents import llm

from runtime.agents import service as agents
from runtime.agents.declaration import Declaration, check_words
from runtime.enums import Channel, Direction, Env
from runtime.exceptions import ValidationError
from runtime.kit.text import Json, JsonObject
from runtime.session.hearing import AgentWords
from runtime.session.writing import WRITTEN_WITHIN_S, Writing
from runtime.wire import parts
from runtime.wire.base import BatchedEntry, Entry
from runtime.wire.commands import CallCallback, CallLog, SessionConfigure, StateSet, ToolsSet
from runtime.wire.events import (
    AgentConfigured,
    CallbackRequested,
    Custom,
    EventReceived,
    StateChanged,
    ToolsChanged,
)
from runtime.wire.metrics import ModelUsage
from runtime.wire.parts import EndedBy, EndReason, EventSource, PlatformTool, StateCause, StateCauseEvent, ToolResult

# `sp_<n>`: numbered on from the highest in the log when a call is taken up again.
SPEECH = "sp_"
# A callback the agent took during a call; others come from the widget or an overflow.
BY_THE_AGENT = "agent"
UNDECLARED = "event {name!r} is not one this agent declared the {source} may send"


@dataclass(frozen=True, slots=True)
class ToolUse:
    """One tool call the model made: its id, the tool, the arguments it chose, and its line."""

    call_id: str
    name: str
    arguments: JsonObject
    # What the model wrote for the caller to hear as the tool runs; "" when it wrote nothing.
    say: str = ""


# What a call is, as the worker and the gateway see it when it starts, is `calls`' value, above this
# domain: a session reads this much of it, and whatever opens the call hands it in.
class Route(Protocol):
    """The route a call came in by, as far as a session reads it."""

    @property
    def agent(self) -> str:
        """The agent that answers."""
        ...

    @property
    def number(self) -> str | None:
        """The number it answers at; None for the widget."""
        ...


class Contact(Protocol):
    """What is known about the caller; a web visitor may be anonymous."""

    @property
    def id(self) -> str | None:
        """The app's own id for them."""
        ...

    @property
    def phone(self) -> str | None:
        """Their number."""
        ...

    @property
    def name(self) -> str | None:
        """Their name."""
        ...

    @property
    def email(self) -> str | None:
        """Their address."""
        ...

    @property
    def external_id(self) -> str | None:
        """Their id in a system of the tenant's."""
        ...


class CallContext(Protocol):
    """A call as it starts: its id, who calls, the route it came in by, its day, what opened it."""

    @property
    def call(self) -> str:
        """The call's id."""
        ...

    @property
    def channel(self) -> Channel:
        """Where the conversation comes in."""
        ...

    @property
    def direction(self) -> Direction:
        """Who called whom."""
        ...

    @property
    def caller(self) -> str:
        """The calling side: a number, or the visitor's id."""
        ...

    @property
    def route(self) -> Route:
        """The route it came in by."""
        ...

    @property
    def env(self) -> Env:
        """The env of the call's route."""
        ...

    @property
    def today(self) -> date:
        """The call's day."""
        ...

    @property
    def pinned_day(self) -> date | None:
        """The day a golden pinned, when one did."""
        ...

    @property
    def contact(self) -> Contact | None:
        """Who is on the line, when the call was opened with somebody."""
        ...

    @property
    def metadata(self) -> Mapping[str, Json]:
        """What the opener attached to the call."""
        ...

    @property
    def run(self) -> str | None:
        """The eval run that opened the call; None for a real caller."""
        ...

    @property
    def persona(self) -> str | None:
        """The simulated caller's name."""
        ...

    @property
    def expects(self) -> tuple[str, ...]:
        """What the simulated caller expects, frozen as the call starts."""
        ...

    @property
    def state(self) -> Mapping[str, Json]:
        """The state the call opens in, when a golden, a persona or the page asked for one."""
        ...

    @property
    def continues(self) -> str | None:
        """The ended call this one carries on."""
        ...

    @property
    def remembered_as(self) -> str | None:
        """The memory key for the caller, or None when the caller is anonymous."""
        ...


# What a session reaches outside the process its call runs in. In the gateway it is the call's own
# log and the endpoints behind it; in a worker, the same endpoints over its client. The session
# never knows which: whatever hosts it implements this and hands it in with the call.
class Platform(Protocol):
    """The log a call writes, the app's tools, the lookups, and the seal at the end."""

    async def append_many(self, entries: list[BatchedEntry], *, after: int) -> list[Entry]:
        """The entries on the call's log, numbered, after the ones it already took from this writer."""
        ...

    async def run_tool(self, use: ToolUse, speech: str | None) -> ToolResult:
        """One of the app's tools run in the app's process, and what came back."""
        ...

    async def look_up(self, tool: PlatformTool, arguments: JsonObject, speech: str | None) -> JsonObject:
        """A recall or a search, written on the call's log and answered as the model reads it."""
        ...

    async def seal(self, usage: list[ModelUsage], outcome: str) -> None:
        """The call is over: what its models used and the last thing it said."""
        ...

    # Tells the gateway, whose seal waits for it, that the app's end hook ran and what it wrote was
    # sent (the app's `call.done`); nothing where nothing waits for it.
    async def release_seal(self) -> None:
        """The app's end hook ran: the seal that waits for it may go on."""
        ...


class Call:
    """One call's state that outlives a turn, and the entries the app's commands write."""

    def __init__(
        self,
        context: CallContext,
        declaration: Declaration,
        platform: Platform,
        recording: Path | None = None,
        carried: llm.ChatContext | None = None,
        *,
        written: int = 0,
    ) -> None:
        """A call nobody has spoken on yet, every tool of its agent open."""
        self.context = context
        self.declaration = declaration
        # The turns of the call it carries on (context.continues), which its model opens on.
        self.carried = carried
        # Where its session records its audio: none for a written call or one the agent keeps none.
        self.recording = recording
        self.platform = platform
        # `written` is how many entries the log already took from the call: a call taken up again
        # goes on from there, never from zero.
        self.writing = Writing(platform.append_many, context.call, after=written)
        self.speeches = 0
        self.turns = 0
        self.last_said = ""
        # What the next state.set is answering: a running tool, or an event the app received.
        self.cause: StateCause | None = None
        # Why the call ended, when our code knows: it wins over livekit's close reason.
        self.ended: tuple[EndReason, EndedBy] | None = None
        # As the session's agent_state events say, not as livekit's internals hold it.
        self.agent_speaking = False
        # What it said lately, so its own voice heard back is not taken for the caller's.
        self.agent_words = AgentWords()
        self.open_tools = frozenset(tool.name for tool in declaration.tools)
        # Every request the model was sent, kept on a call an eval run opened and on no other.
        self.requests: list[JsonObject] = []

    def speech(self) -> str:
        """A new speech id, `sp_<n>`."""
        self.speeches += 1
        return f"{SPEECH}{self.speeches}"

    # A call taken up again goes on counting from where its log left it.
    def resume_from(self, turns: int, last_said: str, speeches: int) -> None:
        """Stand where the call stood when its session went away."""
        self.turns, self.last_said, self.speeches = turns, last_said, speeches

    # livekit's close reason misreads what our code knows: a cold transfer reads as the caller
    # hanging up, end_call as a drain. What is said here is what the call's last entry says.
    def end_as(self, reason: EndReason, by: EndedBy) -> None:
        """Say why the call ends, as our code knows it."""
        self.ended = (reason, by)

    # The app says who wrote it when it knows, which is every write of an SDK: a tool's second
    # write and a hook's are authored too. What the platform saw running is for an app that does not.
    async def set_state(self, wanted: StateSet) -> None:
        """The app's whole state, and what caused it: the app's word, else the tool or event running."""
        changed = wanted.changed if wanted.changed is not None else sorted(wanted.state)
        guessed, self.cause = self.cause, None
        cause = wanted.cause or guessed
        written = StateChanged(state=wanted.state, changed=changed)
        if cause is not None:
            written.cause = cause
        await self.writing.write("state.changed", written)

    # Whoever sends it: the app on its socket, or a widget's seat on the room's data channel. Until
    # 2026-11 the widget wrote its own entry and left no cause for the state.set that answered it.
    async def receive(self, name: str, data: JsonObject, *, source: EventSource, identity: str | None = None) -> None:
        """An event the agent says this sender may send, the cause of the next state.set."""
        if not self.declaration.accepts(name, source):
            raise ValidationError(UNDECLARED.format(name=name, source=source))
        received = EventReceived(name=name, data=data, source=source, identity=identity)
        entry = await self.writing.write("event.received", received)
        self.cause = StateCauseEvent(kind="event", name=name, seq=entry.seq)

    async def log_custom(self, wanted: CallLog) -> None:
        """A line of the app's own, as it sent it."""
        await self.writing.write("custom", Custom(name=wanted.name, data=wanted.data))

    # Every line the app sent before this one is appended already (each command is applied in turn and
    # awaits its write), and what is still queued is flushed first: the seal goes on after the last of them.
    async def app_finished(self) -> None:
        """The app's end hook ran and what it wrote is sent: tell the seal that waits for it."""
        with contextlib.suppress(TimeoutError):
            await self.writing.flush(WRITTEN_WITHIN_S)
        await self.platform.release_seal()

    async def call_back(self, wanted: CallCallback) -> None:
        """A callback the agent took, in the call's log, where the callbacks endpoint collects it."""
        requested = CallbackRequested(
            channel=self.context.channel,
            number=wanted.number,
            via=BY_THE_AGENT,
            call=self.context.call,
            contact=contact_of(self.context),
            when=wanted.when,
            note=wanted.note,
        )
        await self.writing.write("callback.requested", requested)

    # What the app sets up before the first turn; a declaration sent here lasts this call only, and is
    # held to its own words as a class's is, never to the vendors a stage already runs on.
    async def configure(self, wanted: SessionConfigure) -> None:
        """The app's declaration and state for this call."""
        if wanted.config is not None:
            changed = agents.apply_declaration(self.declaration, wanted.config)
            check_words(changed)
            self.declaration = changed
            await self.writing.write("agent.configured", AgentConfigured(changed=agents.list_changes(wanted.config)))
        if wanted.state is not None:
            await self.set_state(StateSet(state=wanted.state))

    # Every tool stays in the agent's hands for the whole call: changing what the provider is sent
    # spends its prompt cache. The subset open now is enforced where a tool is run.
    async def set_tools(self, wanted: ToolsSet) -> None:
        """Open only these of the agent's tools; an empty list closes them all."""
        names = {tool.name for tool in self.declaration.tools}
        self.open_tools = frozenset(tool.name for tool in wanted.tools if tool.name in names)
        await self.writing.write("tools.changed", ToolsChanged(visible=sorted(self.open_tools)))


# Every field said, the unknown ones as null: the entry reads as it always did.
def contact_of(context: CallContext) -> parts.Contact | None:
    """Who the call was opened with, as the wire names them; None when nobody was named."""
    contact = context.contact
    if contact is None:
        return None
    return parts.Contact(
        id=contact.id, phone=contact.phone, name=contact.name, email=contact.email, external_id=contact.external_id
    )
