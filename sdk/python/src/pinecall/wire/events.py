"""Every event a log holds and the registry of them; the agent's and the control's defined here."""

from typing import Literal

from pydantic import Field

from pinecall.errors import WireError
from pinecall.wire._names import Channel, Env, JsonObject, QuotaName
from pinecall.wire.events_call import (
    AttentionAnswered,
    AttentionRequested,
    CallAttached,
    CallClaimed,
    CallDialing,
    CallEnded,
    CallLine,
    CallRinging,
    CallStarted,
    CallSummary,
    CallTransferred,
    ConfirmDeclined,
    ConfirmGranted,
    ConfirmRequest,
    SupervisorEnded,
    SupervisorReleased,
    SupervisorSaid,
    SupervisorTookOver,
    SupervisorTransferred,
    SupervisorWhispered,
)
from pinecall.wire.events_turn import (
    AgentStateChanged,
    AgentTranscript,
    AgentTurnEnded,
    Custom,
    DocsSources,
    DtmfReceived,
    EventReceived,
    MemoryOps,
    PromptChanged,
    StateChanged,
    ToolCall,
    ToolsChanged,
    UserStateChanged,
    UserTranscript,
    UserTurnEnded,
    VendorSwitched,
)
from pinecall.wire.frames import Entry, WireModel
from pinecall.wire.metrics import (
    AvatarMetrics,
    EOTInferenceMetrics,
    EOUMetrics,
    InterruptionMetrics,
    LLMMetrics,
    RealtimeModelMetrics,
    STTMetrics,
    TTSMetrics,
    VADMetrics,
)
from pinecall.wire.parts import (
    Contact,
    DevVerb,
    Projection,
    Route,
    ToolResult,
)
from pinecall.wire.room import (
    ParticipantJoined,
    ParticipantLeft,
    ParticipantSpeaking,
    RoomOpened,
    RoomSent,
    TrackPublished,
    TrackUnpublished,
)
from pinecall.wire.scores import CallScore
from pinecall.wire.state import State

# Events a store may drop and a slow reader may miss: the entry's ephemeral flag defaults to this.
EPHEMERAL_EVENTS: frozenset[str] = frozenset(
    {
        "agent.transcript",
        "dev.request",
        "judge.broke",
        "log.caught_up",
        "log.gap",
        "metrics.vad",
        "participant.speaking",
        "pong",
        "release.changed",
        "room.sent",
        "run.changed",
        "tool.failed",
        "tool.ran",
        "user.transcript",
        "worker.changed",
    }
)


# The one event that ends a call: after it nothing more is true and the log is sealed.
TERMINAL_EVENT = "call.score"


# What the gateway writes on a call's log itself, and no worker ever does: the arrival, a code
# claimed, a socket attached, the summary and the score, memory and sources, and the markers a
# reader is sent and no store keeps. The append doors refuse these from anybody.
GATEWAY_WRITES: frozenset[str] = frozenset(
    {
        "call.ringing",
        "call.dialing",
        "call.attached",
        "call.claimed",
        "call.summary",
        "call.score",
        "memory.ops",
        "docs.sources",
        "log.gap",
        "log.caught_up",
    }
)


class AgentConfigured(WireModel):
    """The gateway applied an agent.configure; the next call starts with the new config."""

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


class CallbackRequested(WireModel):
    """Somebody asked to be called back; written into the agent's own log."""

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


class CreditsExhausted(WireModel):
    """The gateway refused a call, a turn or a register because one of the org's quotas ran out."""

    org: str
    quota: QuotaName
    used: float
    limit: int


class EvalsSpent(WireModel):
    """The harness asked a model outside a call's score: a judge tried, personas, a diagnosis."""

    kind: Literal["try", "generate", "propose"]
    name: str
    # The agent's log is both worlds': the try is counted in the one it was asked in.
    env: Env
    calls: list[str]
    evals: int
    judge_calls: int
    judge_cost_usd: float | None = None
    own_key: bool = False


class SpendUnusual(WireModel):
    """The org's calls cost more today than its own days usually do: said once a day."""

    org: str
    day: str
    today_usd: float
    usual_usd: float
    multiple: float


class DevRequest(WireModel):
    """One ask of the process in the agent's directory, on a console's behalf."""

    id: str
    verb: DevVerb
    data: JsonObject


class ErrorEvent(WireModel):
    """Something went wrong: what failed in a call, or which command the gateway refused."""

    code: str
    message: str
    command: str | None = None
    id: str | None = None
    recoverable: bool


class FleetFull(WireModel):
    """The gateway refused to open a call because every worker of the fleet was full."""

    channel: Channel
    workers: int
    active: int


class ReleaseChanged(WireModel):
    """A hosted app's release changed where it stands: uploaded, live, failed or replaced."""

    app: str
    release: int


class RunChanged(WireModel):
    """A run of goldens and cases opened a call, judged one, or finished."""

    run: str
    agent: str
    finished: bool


class WorkerChanged(WireModel):
    """A worker of a fleet was first heard, cordoned, uncordoned, or stopped being heard."""

    worker: str
    fleet: str
    up: bool
    cordoned: bool


class ToolRan(WireModel):
    """A tool of a call answered; its name and seconds, never its arguments or its output."""

    call: str
    agent: str
    name: str
    duration_s: float | None


class ToolFailed(WireModel):
    """A tool of a call failed or timed out; its name and seconds, never what it said."""

    call: str
    agent: str
    name: str
    duration_s: float | None


class JudgeBroke(WireModel):
    """A judge found a sealed call broken; its name, never its reason or its evidence."""

    call: str
    agent: str
    judge: str


class LogCaughtUp(WireModel):
    """The replay is done: everything up to seq has been sent and what follows is live."""

    seq: int


class LogGap(WireModel):
    """This reader missed a stretch; the snapshot, when there is one, catches it up in one step."""

    from_seq: int
    to_seq: int
    snapshot: State | None


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
    "judge.broke": JudgeBroke,
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
    "participant.joined": ParticipantJoined,
    "participant.left": ParticipantLeft,
    "participant.speaking": ParticipantSpeaking,
    "pong": Pong,
    "prompt.changed": PromptChanged,
    "release.changed": ReleaseChanged,
    "room.opened": RoomOpened,
    "room.sent": RoomSent,
    "state.changed": StateChanged,
    "run.changed": RunChanged,
    "spend.unusual": SpendUnusual,
    "supervisor.ended": SupervisorEnded,
    "supervisor.released": SupervisorReleased,
    "supervisor.said": SupervisorSaid,
    "supervisor.took_over": SupervisorTookOver,
    "supervisor.transferred": SupervisorTransferred,
    "supervisor.whispered": SupervisorWhispered,
    "tool.call": ToolCall,
    "tool.failed": ToolFailed,
    "tool.ran": ToolRan,
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
    """Return the entry's data as the model its type names; an unknown type is refused."""
    model = EVENTS.get(entry.type)
    if model is None:
        raise WireError(f"unknown event type: {entry.type}")
    return model.read(entry.data, entry.type)
