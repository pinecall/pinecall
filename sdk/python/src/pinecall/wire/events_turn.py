"""What happens inside a conversation: the turns, the tools, the state, an outside fact."""

from typing import Annotated, Literal, TypeAlias

from pydantic import Field

from pinecall.wire._names import EventSource, JsonObject
from pinecall.wire.frames import WireModel
from pinecall.wire.metrics import (
    AgentTurnMetrics,
    UserTurnMetrics,
)
from pinecall.wire.parts import (
    AgentState,
    DocSource,
    MemoryOp,
    UserState,
)


class EventReceived(WireModel):
    """A fact arrived from outside the conversation, from the app or a participant's browser."""

    name: str
    data: JsonObject
    source: EventSource
    identity: str | None = None


class AgentStateChanged(WireModel):
    """The agent's state changed, in the session's own words."""

    state: AgentState


class AgentTranscript(WireModel):
    """One delta of the reply the agent is giving, never the reply so far."""

    speech_id: str
    text: str
    final: bool
    start: float | None = None
    end: float | None = None


class Custom(WireModel):
    """A line the app wrote into the log with call.log; the platform never reads it."""

    name: str
    data: JsonObject


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


class MemoryOps(WireModel):
    """What memory did for this turn or at hangup."""

    ops: list[MemoryOp]
    speech_id: str | None = None


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


StateCause: TypeAlias = Annotated[StateCauseTool | StateCauseEvent, Field(discriminator="kind")]


class StateChanged(WireModel):
    """The app's declared state changed; the whole state travels."""

    state: JsonObject
    changed: list[str]
    cause: StateCause | None = None


class ToolCall(WireModel):
    """The model called a tool; tool.result closes it."""

    call_id: str
    name: str
    arguments: JsonObject
    speech_id: str | None = None


class ToolsChanged(WireModel):
    """The tools the model can see changed."""

    visible: list[str]


class AgentTurnEnded(WireModel):
    """The agent's reply is over and this is what was said."""

    speech_id: str
    item_id: str | None = None
    text: str
    interrupted: bool
    metrics: AgentTurnMetrics


class UserTurnEnded(WireModel):
    """The caller's turn is over and this is what they said."""

    speech_id: str
    item_id: str | None = None
    text: str
    language: str | None = None
    transcript_confidence: float | None = None
    metrics: UserTurnMetrics


class UserStateChanged(WireModel):
    """The caller's state changed, in the session's own words."""

    state: UserState


class UserTranscript(WireModel):
    """Words from the caller as the recognizer hears them; the final one becomes turn.user."""

    text: str
    final: bool
    language: str | None = None
    confidence: float | None = None


class VendorSwitched(WireModel):
    """A stage's vendor failed or came back; `serving` is the vendor the stage runs on now."""

    stage: Literal["llm", "stt", "tts"]
    vendor: str
    model: str
    available: bool
    serving: str
    serving_model: str
