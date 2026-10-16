"""What a call is while it runs, spoken or written: its state, and what the app's commands write."""

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path

from livekit.agents import llm

from pinecall_runtime.agents.declaration import AgentConfig
from pinecall_runtime.agents.service import declared
from pinecall_runtime.calls.context import CallContext
from pinecall_runtime.exceptions import ValidationError
from pinecall_runtime.kit.text import JsonObject
from pinecall_runtime.session.hearing import TurnPolicy, policy_for
from pinecall_runtime.session.writing import AppendMany, Writing
from pinecall_runtime.wire.commands import (
    CallCallback,
    CallLog,
    SessionConfigure,
    StateSet,
    ToolsSet,
)
from pinecall_runtime.wire.events import (
    AgentConfigured,
    CallbackRequested,
    Custom,
    EventReceived,
    StateCause,
    StateCauseEvent,
    StateChanged,
    ToolsChanged,
)
from pinecall_runtime.wire.metrics import ModelUsage
from pinecall_runtime.wire.parts import Contact, EventSource, PlatformTool, Supervisor, ToolResult

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


type RunTool = Callable[[ToolUse, str | None], Awaitable[ToolResult]]
type Lookup = Callable[[PlatformTool, JsonObject, str | None], Awaitable[JsonObject]]
type Seal = Callable[[list[ModelUsage], str], Awaitable[None]]


# What a session reaches outside the process its call runs in. In the gateway these are the
# call's own log and the endpoints behind it; in a worker, the same endpoints over its client.
@dataclass(frozen=True, slots=True)
class Platform:
    """The log a call writes, the app's tools, the lookups, and the seal at the end."""

    append_many: AppendMany
    tool: RunTool
    lookup: Lookup
    seal: Seal


class Call:
    """One call's state that outlives a turn, and the entries the app's commands write."""

    def __init__(
        self,
        context: CallContext,
        config: AgentConfig,
        platform: Platform,
        recording: Path | None = None,
        carried: llm.ChatContext | None = None,
    ) -> None:
        """A call nobody has spoken on yet, every declared tool open."""
        self.context = context
        self.config = config
        # The turns of the call it carries on (context.continues), which its model opens on.
        self.carried = carried
        # Where its session records its audio: none for a written call or one the agent keeps none.
        self.recording = recording
        self.turn_policy: TurnPolicy = policy_for(config.language)
        self.platform = platform
        self.writing = Writing(platform.append_many, context.call)
        self.speeches = 0
        self.turns = 0
        self.last_said = ""
        # What the next state.set is answering: a running tool, or an event the app received.
        self.cause: StateCause | None = None
        self.taken_by: Supervisor | None = None
        self.waiting_for_a_person = False
        # As the session's agent_state events say, not as livekit's internals hold it.
        self.agent_speaking = False
        self.open_tools = frozenset(tool.name for tool in config.tools)
        # Every request the model was sent, kept on a call an eval run opened and on no other.
        self.requests: list[JsonObject] = []
        # When the caller last stopped speaking, until the agent's first turn after it is written.
        self.heard_stopped_at: float | None = None

    def speech(self) -> str:
        """A new speech id, `sp_<n>`."""
        self.speeches += 1
        return f"{SPEECH}{self.speeches}"

    def heard(self, metrics: Mapping[str, object]) -> None:
        """The caller's turn ended: the agent's next turn is the first sound they wait for."""
        stopped = metrics.get("stopped_speaking_at")
        self.heard_stopped_at = float(stopped) if isinstance(stopped, int | float) else None

    # livekit's e2e_latency runs from the caller's last word to the turn it rides on, so a preamble
    # said before a tool ("let me look that up") left the tool's wait on the answer after it. The
    # caller waits for the first sound: the first turn after theirs carries that, a later one none.
    def replied(self, metrics: Mapping[str, object]) -> dict[str, object]:
        """An agent turn's metrics, e2e_latency the caller's wait to it; none on a later turn."""
        answer = dict(metrics)
        stopped, self.heard_stopped_at = self.heard_stopped_at, None
        started = answer.get("started_speaking_at")
        if stopped is not None and isinstance(started, int | float) and started >= stopped:
            answer["e2e_latency"] = float(started) - stopped
        else:
            answer.pop("e2e_latency", None)
        return answer

    @property
    def a_person_has_the_line(self) -> bool:
        """Whether the model must not answer: a supervisor holds the line, or one is awaited."""
        return self.taken_by is not None or self.waiting_for_a_person

    async def set_state(self, wanted: StateSet) -> None:
        """The app's whole state, and what it answers when a tool or an event caused it."""
        changed = wanted.changed if wanted.changed is not None else sorted(wanted.state)
        cause, self.cause = self.cause, None
        written = StateChanged(state=wanted.state, changed=changed)
        if cause is not None:
            written.cause = cause
        await self.writing.write("state.changed", written)

    async def receive(self, name: str, data: JsonObject, *, source: EventSource, identity: str | None = None) -> None:
        """An event the agent declared this sender may send, the cause of the next state.set."""
        if not self.config.accepts(name, source):
            raise ValidationError(UNDECLARED.format(name=name, source=source))
        received = EventReceived(name=name, data=data, source=source, identity=identity)
        entry = await self.writing.write("event.received", received)
        self.cause = StateCauseEvent(kind="event", name=name, seq=entry.seq)

    async def log_custom(self, wanted: CallLog) -> None:
        """A line of the app's own, as it sent it."""
        await self.writing.write("custom", Custom(name=wanted.name, data=wanted.data))

    async def call_back(self, wanted: CallCallback) -> None:
        """A callback the agent took, in the call's log, where the callbacks endpoint collects it."""
        contact = self.context.contact
        requested = CallbackRequested(
            channel=self.context.channel,
            number=wanted.number,
            via=BY_THE_AGENT,
            call=self.context.call,
            contact=None if contact is None else Contact.model_validate(asdict(contact)),
            when=wanted.when,
            note=wanted.note,
        )
        await self.writing.write("callback.requested", requested)

    # What the app sets up before the first turn; a declaration sent here lasts this call only.
    async def configure(self, wanted: SessionConfigure) -> None:
        """The app's declaration and state for this call."""
        if wanted.config is not None:
            self.config = declared.with_app_fields(self.config, wanted.config)
            await self.writing.write("agent.configured", AgentConfigured(changed=declared.changed_by(wanted.config)))
        if wanted.state is not None:
            await self.set_state(StateSet(state=wanted.state))

    # Every tool stays declared for the whole call: changing what the provider is sent spends
    # its prompt cache. The subset open now is enforced where a tool is run.
    async def set_tools(self, wanted: ToolsSet) -> None:
        """Open only these of the declared tools; an empty list closes them all."""
        names = {tool.name for tool in self.config.tools}
        self.open_tools = frozenset(tool.name for tool in wanted.tools if tool.name in names)
        await self.writing.write("tools.changed", ToolsChanged(visible=sorted(self.open_tools)))
