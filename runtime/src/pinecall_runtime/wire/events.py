"""Every event a log holds, and the registry that maps a type to its shape."""

from typing import Annotated, Any, Literal

from pydantic import Field

from pinecall_runtime.enums import Channel, Direction, Env, Medium
from pinecall_runtime.exceptions import ValidationError
from pinecall_runtime.wire.base import Entry, WireModel
from pinecall_runtime.wire.feed import ReleaseChanged, RunChanged, WorkerChanged
from pinecall_runtime.wire.metrics import (
    AgentTurnMetrics,
    AvatarMetrics,
    EOTInferenceMetrics,
    EOUMetrics,
    InterruptionMetrics,
    LLMMetrics,
    ModelUsage,
    RealtimeModelMetrics,
    STTMetrics,
    TTSMetrics,
    UserTurnMetrics,
    VADMetrics,
)
from pinecall_runtime.wire.parts import (
    AgentState,
    Contact,
    Cost,
    DevVerb,
    DocSource,
    EndedBy,
    EndReason,
    EventSource,
    MemoryOp,
    Projection,
    QuotaName,
    Route,
    Supervisor,
    ToolResult,
    TransferMode,
    UserState,
)
from pinecall_runtime.wire.room import (
    ParticipantJoined,
    ParticipantLeft,
    ParticipantSpeaking,
    RoomOpened,
    RoomSent,
    TrackPublished,
    TrackUnpublished,
)
from pinecall_runtime.wire.scores import CallScore, EvalsSpent
from pinecall_runtime.wire.state import State

# Events a store may drop and a slow reader may miss.
EPHEMERAL_EVENTS: frozenset[str] = frozenset(
    {
        "agent.transcript",
        "dev.request",
        "log.caught_up",
        "log.gap",
        "metrics.vad",
        "participant.speaking",
        "pong",
        "release.changed",
        "room.sent",
        "run.changed",
        "user.transcript",
        "worker.changed",
    }
)

# The one event that ends a call: after it the log is sealed.
TERMINAL_EVENT = "call.score"

# What the gateway writes on a call's log itself and no worker ever does.
GATEWAY_WRITES: frozenset[str] = frozenset(
    {
        "call.ringing",
        "call.dialing",
        "call.attached",
        "call.claimed",
        "call.summary",
        "call.score",
        "evals.spent",
        "memory.ops",
        "docs.sources",
        "log.gap",
        "log.caught_up",
    }
)


class EventReceived(WireModel):
    """A fact arrived from outside the conversation."""

    name: str
    data: dict[str, Any]
    source: EventSource
    identity: str | None = None


class AgentConfigured(WireModel):
    """The gateway applied an agent.configure."""

    changed: list[str]


class AgentDetached(WireModel):
    """One socket stopped holding the agent."""

    app: str
    env: Env
    left: bool


class AgentDraining(WireModel):
    """One socket let go of its calls without cutting them."""

    app: str
    env: Env
    handed: int
    parked: int


class AgentRegistered(WireModel):
    """The gateway accepted an agent.register: this socket now speaks for the agent."""

    routes: list[Route]
    app: str
    sdk: str | None = None
    env: Env | None = None


class AgentStateChanged(WireModel):
    """The agent's state changed."""

    state: AgentState


class AgentTranscript(WireModel):
    """One delta of the reply the agent is giving."""

    speech_id: str
    text: str
    final: bool
    start: float | None = None
    end: float | None = None


class AttentionAnswered(WireModel):
    """An ask for a person settled."""

    ok: bool
    by: Supervisor | None
    error: str | None = None


class AttentionRequested(WireModel):
    """The agent asked for a person: the caller is on hold until a supervisor takes the line."""

    reason: str
    wait_s: float


class CallStarted(WireModel):
    """Media is up, or the text session is open."""

    channel: Channel
    direction: Direction
    from_: str = Field(alias="from")
    to: str
    run: str | None = None
    persona: str | None = None
    expects: list[str] | None = None
    accepts_when: str | None = Field(default=None, exclude=True)
    declines_when: str | None = Field(default=None, exclude=True)
    caller: Contact | None
    started_at: float
    env: Env | None = None
    worker: str | None = None
    medium: Medium | None = None
    state: dict[str, Any] | None = None
    today: str | None = None


class CallAttached(WireModel):
    """A call changed hands without ending."""

    app: str
    started: CallStarted
    state: dict[str, Any]
    seq: int
    claimed: str | None = None


class CallClaimed(WireModel):
    """The call was bound to a page's code."""

    code: str
    via: Literal["keypad", "agent"]


class CallDialing(WireModel):
    """The platform is placing an outbound call."""

    channel: Channel
    from_: str = Field(alias="from")
    to: str
    run: str | None = None
    caller: Contact | None
    external_id: str | None = None
    asked_by: str | None = None


class CallEnded(WireModel):
    """The call is over; call.summary still follows."""

    reason: EndReason
    ended_by: EndedBy
    ended_at: float
    duration_s: float


class CallLine(WireModel):
    """The line's hold and mute flags after one changed."""

    held: bool
    muted: bool


class CallRinging(WireModel):
    """An inbound call is offered to this agent."""

    channel: Channel
    from_: str = Field(alias="from")
    to: str
    route: Route
    run: str | None = None
    caller: Contact | None
    external_id: str | None = None


class CallSummary(WireModel):
    """What the call was about, how it went, what it consumed and what that cost."""

    reason: EndReason
    outcome: str
    duration_s: float
    turns: int
    usage: list[ModelUsage]
    cost: Cost
    recording: str | None = None
    simulated: bool = False
    run: str | None = None


class CallTransferred(WireModel):
    """A transfer finished, one way or the other."""

    to: str
    mode: TransferMode | None = None
    ok: bool
    error: str | None = None


class CallbackRequested(WireModel):
    """Somebody asked to be called back; on the agent's own log."""

    channel: Channel
    number: str
    via: Literal["overflow", "widget", "agent"]
    call: str | None
    when: str | None = None
    note: str | None = None
    contact: Contact | None


class CodeClaimed(WireModel):
    """One code, taken or expired."""

    code: str
    call: str | None


class CodeIssued(WireModel):
    """One code, waiting for the call that keys it."""

    code: str
    env: Env
    expires_at: float
    log: Projection


class ConfirmDeclined(WireModel):
    """The caller did not say yes, or the request lapsed."""

    tool: str
    call_id: str
    audience: str
    said: str | None = None
    reason: Literal["no", "timeout", "changed", "cancelled"]


class ConfirmGranted(WireModel):
    """The caller said yes."""

    tool: str
    call_id: str
    audience: str
    said: str
    ttl_s: int


class ConfirmRequest(WireModel):
    """A tool with confirm set is about to run and the platform is asking the caller."""

    tool: str
    call_id: str
    arguments: dict[str, Any]
    audience: str
    phrase: str
    ttl_s: int


class CreditsExhausted(WireModel):
    """The gateway refused something because one of the org's quotas ran out."""

    org: str
    quota: QuotaName
    used: float
    limit: int


class MonitorFired(WireModel):
    """A monitor's number crossed its line over its window."""

    monitor: str
    name: str
    metric: str
    above: bool
    threshold: float
    value: float
    window_days: int
    agent: str | None
    env: Env
    day: str


class SpendUnusual(WireModel):
    """The org's calls cost more today than its own days usually do."""

    org: str
    day: str
    today_usd: float
    usual_usd: float
    multiple: float


class Custom(WireModel):
    """A line the app wrote into the log with call.log."""

    name: str
    data: dict[str, Any]


class DevRequest(WireModel):
    """One ask of the process in the agent's directory, on a console's behalf."""

    id: str
    verb: DevVerb
    data: dict[str, Any]


class DocsSources(WireModel):
    """What retrieval put in front of the model for this turn."""

    query: str
    sources: list[DocSource]
    took_ms: float
    speech_id: str | None = None


class DtmfReceived(WireModel):
    """One tone the caller keyed."""

    digit: Literal["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "*", "#"]
    code: int


class ErrorEvent(WireModel):
    """Something went wrong: what failed, or which command the gateway refused."""

    code: str
    message: str
    command: str | None = None
    id: str | None = None
    recoverable: bool


class FleetFull(WireModel):
    """The gateway refused to open a call because every worker was full."""

    channel: Channel
    workers: int
    active: int


class LogCaughtUp(WireModel):
    """The replay is done; what follows is live."""

    seq: int


class LogGap(WireModel):
    """This reader missed a stretch; the snapshot catches it up in one step."""

    from_seq: int
    to_seq: int
    snapshot: State | None


class MemoryOps(WireModel):
    """What memory did for this turn or at hang-up."""

    ops: list[MemoryOp]
    speech_id: str | None = None


class MessageTaken(WireModel):
    """One waiting message, off the queue."""

    message_id: str
    call: str | None


class MessageWaiting(WireModel):
    """One message, kept until somebody can answer it."""

    channel: Channel
    env: Env
    number: str
    phone_number_id: str
    from_: str = Field(alias="from")
    name: str | None
    message_id: str
    text: str
    received_at: float


class Pong(WireModel):
    """The answer to ping."""

    ts: float


class PromptChanged(WireModel):
    """A block of the prompt was rewritten; its hash and length, never its text."""

    name: str
    hash: str
    chars: int


class StateCauseTool(WireModel):
    """A tool call's result changed the state."""

    kind: Literal["tool"] = "tool"
    tool: str
    call_id: str


class StateCauseEvent(WireModel):
    """A fact from outside changed the state."""

    kind: Literal["event"] = "event"
    name: str
    seq: int


type StateCause = Annotated[StateCauseTool | StateCauseEvent, Field(discriminator="kind")]


class StateChanged(WireModel):
    """The app's declared state changed; the whole state travels."""

    state: dict[str, Any]
    changed: list[str]
    cause: StateCause | None = None


class SupervisorEnded(WireModel):
    """A supervisor hung up the call."""

    by: Supervisor
    reason: str | None = None


class SupervisorReleased(WireModel):
    """The supervisor gave the line back."""

    by: Supervisor


class SupervisorSaid(WireModel):
    """A supervisor made the agent say this."""

    by: Supervisor
    text: str


class SupervisorTookOver(WireModel):
    """A supervisor took the line."""

    by: Supervisor


class SupervisorTransferred(WireModel):
    """A supervisor asked for a transfer."""

    by: Supervisor
    to: str
    mode: TransferMode | None = None


class SupervisorWhispered(WireModel):
    """A supervisor told the agent something the caller never heard."""

    by: Supervisor
    text: str


class ToolCall(WireModel):
    """The model called a tool; tool.result closes it."""

    call_id: str
    name: str
    arguments: dict[str, Any]
    speech_id: str | None = None


class ToolsChanged(WireModel):
    """The tools the model can see changed."""

    visible: list[str]


class AgentTurnEnded(WireModel):
    """The agent's reply is over."""

    speech_id: str
    item_id: str | None = None
    text: str
    interrupted: bool
    metrics: AgentTurnMetrics


class UserTurnEnded(WireModel):
    """The caller's turn is over."""

    speech_id: str
    item_id: str | None = None
    text: str
    language: str | None = None
    transcript_confidence: float | None = None
    metrics: UserTurnMetrics


class UserStateChanged(WireModel):
    """The caller's state changed."""

    state: UserState


class UserTranscript(WireModel):
    """Words from the caller as the recognizer hears them."""

    text: str
    final: bool
    language: str | None = None
    confidence: float | None = None


class VendorSwitched(WireModel):
    """A stage's vendor failed or came back; `serving` is what the stage runs on now."""

    stage: Literal["llm", "stt", "tts"]
    vendor: str
    model: str
    available: bool
    serving: str
    serving_model: str


EVENTS: dict[str, type[WireModel]] = {
    "agent.configured": AgentConfigured,
    "agent.detached": AgentDetached,
    "agent.draining": AgentDraining,
    "agent.registered": AgentRegistered,
    "agent.state": AgentStateChanged,
    "agent.transcript": AgentTranscript,
    "attention.answered": AttentionAnswered,
    "attention.requested": AttentionRequested,
    "call.attached": CallAttached,
    "call.claimed": CallClaimed,
    "call.dialing": CallDialing,
    "call.ended": CallEnded,
    "call.line": CallLine,
    "call.ringing": CallRinging,
    "call.score": CallScore,
    "call.started": CallStarted,
    "call.summary": CallSummary,
    "call.transferred": CallTransferred,
    "callback.requested": CallbackRequested,
    "code.claimed": CodeClaimed,
    "code.issued": CodeIssued,
    "confirm.declined": ConfirmDeclined,
    "confirm.granted": ConfirmGranted,
    "confirm.request": ConfirmRequest,
    "credits.exhausted": CreditsExhausted,
    "evals.spent": EvalsSpent,
    "custom": Custom,
    "dev.request": DevRequest,
    "docs.sources": DocsSources,
    "dtmf.received": DtmfReceived,
    "error": ErrorEvent,
    "event.received": EventReceived,
    "fleet.full": FleetFull,
    "log.caught_up": LogCaughtUp,
    "log.gap": LogGap,
    "memory.ops": MemoryOps,
    "message.taken": MessageTaken,
    "message.waiting": MessageWaiting,
    "metrics.avatar": AvatarMetrics,
    "metrics.eot": EOTInferenceMetrics,
    "metrics.eou": EOUMetrics,
    "metrics.interruption": InterruptionMetrics,
    "metrics.llm": LLMMetrics,
    "metrics.realtime": RealtimeModelMetrics,
    "metrics.stt": STTMetrics,
    "metrics.tts": TTSMetrics,
    "metrics.vad": VADMetrics,
    "monitor.fired": MonitorFired,
    "participant.joined": ParticipantJoined,
    "participant.left": ParticipantLeft,
    "participant.speaking": ParticipantSpeaking,
    "pong": Pong,
    "prompt.changed": PromptChanged,
    "release.changed": ReleaseChanged,
    "room.opened": RoomOpened,
    "room.sent": RoomSent,
    "run.changed": RunChanged,
    "spend.unusual": SpendUnusual,
    "state.changed": StateChanged,
    "supervisor.ended": SupervisorEnded,
    "supervisor.released": SupervisorReleased,
    "supervisor.said": SupervisorSaid,
    "supervisor.took_over": SupervisorTookOver,
    "supervisor.transferred": SupervisorTransferred,
    "supervisor.whispered": SupervisorWhispered,
    "tool.call": ToolCall,
    "tool.result": ToolResult,
    "tools.changed": ToolsChanged,
    "track.published": TrackPublished,
    "track.unpublished": TrackUnpublished,
    "turn.agent": AgentTurnEnded,
    "turn.user": UserTurnEnded,
    "user.state": UserStateChanged,
    "user.transcript": UserTranscript,
    "vendor.switched": VendorSwitched,
    "worker.changed": WorkerChanged,
}


def event_of(entry: Entry) -> WireModel:
    """The entry's data as the model its type names; an unknown type is refused."""
    model = EVENTS.get(entry.type)
    if model is None:
        raise ValidationError(f"unknown event type: {entry.type}")
    return model.parse(entry.data, entry.type)
