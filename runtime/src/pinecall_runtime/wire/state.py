"""What a log reduces to: State and its parts."""

from typing import Annotated, Any, Literal

from pydantic import Field

from pinecall_runtime.enums import Channel, Direction
from pinecall_runtime.kit.text import Json
from pinecall_runtime.wire.base import WireModel
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
    CallStatus,
    Contact,
    Cost,
    DocSource,
    EndReason,
    EventSource,
    MemoryOp,
    ParticipantKind,
    Route,
    Supervisor,
    TransferMode,
    UserState,
)


class UserTurn(WireModel):
    """One finished turn of the caller."""

    role: Literal["user"] = "user"
    speech_id: str
    item_id: str | None = None
    text: str
    language: str | None = None
    transcript_confidence: float | None = None
    metrics: UserTurnMetrics


class AgentTurn(WireModel):
    """One finished reply of the agent."""

    role: Literal["agent"] = "agent"
    speech_id: str
    item_id: str | None = None
    text: str
    interrupted: bool
    metrics: AgentTurnMetrics


type Turn = Annotated[UserTurn | AgentTurn, Field(discriminator="role")]


class CollectedMetrics(WireModel):
    """Every raw metric block of the call, by kind, in order."""

    llm: list[LLMMetrics]
    stt: list[STTMetrics]
    tts: list[TTSMetrics]
    vad: list[VADMetrics]
    eou: list[EOUMetrics]
    eot: list[EOTInferenceMetrics]
    interruption: list[InterruptionMetrics]
    realtime: list[RealtimeModelMetrics]
    avatar: list[AvatarMetrics]


class ToolRun(WireModel):
    """One tool call and, once the app answered, its result."""

    call_id: str
    name: str
    arguments: dict[str, Any]
    speech_id: str | None = None
    status: Literal["running", "done", "failed"]
    output: Json = None
    error: str | None = None
    summary: str | None = None
    duration_s: float | None = None
    seq: int


class PromptBlockState(WireModel):
    """What is known about one block of the prompt without its text."""

    hash: str
    chars: int
    seq: int


type PromptState = dict[str, PromptBlockState]


class Confirm(WireModel):
    """One confirmation the platform asked for, and how it went."""

    tool: str
    call_id: str
    audience: str
    phrase: str
    status: Literal["pending", "granted", "declined"]
    said: str | None = None
    reason: str | None = None


class Handoff(WireModel):
    """Whether a supervisor holds the line right now."""

    active: bool
    by: Supervisor | None


class TransferState(WireModel):
    """The transfer in flight or the one that happened."""

    to: str
    mode: TransferMode | None = None
    status: Literal["requested", "done", "failed"]
    by: Literal["agent", "supervisor"]


class AttentionState(WireModel):
    """The agent's last ask for a person."""

    reason: str
    wait_s: float
    status: Literal["open", "answered", "lapsed"]
    asked_at: float
    by: Supervisor | None


class LiveTranscript(WireModel):
    """The words on screen right now."""

    user: str | None
    agent: str | None


class Gap(WireModel):
    """A stretch of seqs this reader never saw."""

    from_seq: int
    to_seq: int


class LoggedError(WireModel):
    """An error entry."""

    seq: int
    code: str
    message: str


class Participant(WireModel):
    """One participant in the room right now."""

    identity: str
    kind: ParticipantKind
    name: str | None = None
    joined_at: float
    speaking: bool
    attributes: dict[str, Any]


class Room(WireModel):
    """The LiveKit room the call lives in, and who is in it."""

    name: str
    sid: str
    participants: list[Participant]
    caller: str | None


class ReceivedEvent(WireModel):
    """One fact that reached the agent from outside."""

    seq: int
    name: str
    source: EventSource
    identity: str | None = None


class CustomNote(WireModel):
    """A line the app wrote into the log."""

    seq: int
    name: str
    data: dict[str, Any]


class State(WireModel):
    """The whole of what a log says, at the seq it was read to."""

    seq: int
    agent: str
    call: str | None
    status: CallStatus
    channel: Channel | None
    direction: Direction | None
    from_: str | None = Field(alias="from")
    to: str | None
    caller: Contact | None
    room: Room | None
    started_at: float | None
    ended_at: float | None
    end_reason: EndReason | None
    outcome: str | None
    user_state: UserState | None
    agent_state: AgentState | None
    live: LiveTranscript
    turns: list[Turn]
    metrics: CollectedMetrics
    tools: list[ToolRun]
    app_state: dict[str, Any]
    events: list[ReceivedEvent]
    prompt: PromptState
    tools_visible: list[str]
    confirms: list[Confirm]
    memory: list[MemoryOp]
    sources: list[DocSource]
    handoff: Handoff
    held: bool
    muted: bool
    transfer: TransferState | None
    attention: AttentionState | None = None
    usage: list[ModelUsage]
    cost: Cost | None
    routes: list[Route]
    gaps: list[Gap]
    errors: list[LoggedError]
    custom: list[CustomNote]
