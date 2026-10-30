"""The parts events, commands and state share: the wire's words and its common shapes."""

from typing import Annotated, Literal, TypeAlias

from pydantic import AliasChoices, Field

from pinecall.wire._names import Channel, Json, JsonObject
from pinecall.wire.frames import WireModel

# What a console may ask of the process standing in the agent's directory, relayed by the gateway.
DevVerb: TypeAlias = Literal[
    "chat.roster",
    "chat.start",
    "chat.say",
    "chat.end",
    "view.render",
    "simulate.start",
    "goldens.roster",
    "goldens.run",
    "knowledge.roster",
    "knowledge.push",
    "knowledge.eval",
    "memory.roster",
    "memory.eval",
    "memory.extraction",
    "promote.roster",
    "promote.write",
    "personas.write",
    "drift.read",
    "reproductions.roster",
    "reproductions.read",
]

# drained: the worker went down with the call on it; app_detached: the app closed mid-call.
# Who says the caller's turn is over: the ears themselves, livekit's detector, or Smart Turn v3.
EndOfTurn: TypeAlias = Literal["stt", "livekit", "smart-turn"]

EndReason: TypeAlias = Literal[
    "caller_hung_up",
    "agent_hung_up",
    "supervisor_ended",
    "transferred",
    "no_answer",
    "busy",
    "dial_failed",
    "timeout",
    "drained",
    "app_detached",
    "error",
]

# platform covers timeouts, errors and a drained worker.
EndedBy: TypeAlias = Literal["caller", "agent", "supervisor", "platform"]

# classified: a choice or a score answered; na: the question did not apply; skipped: nobody
# asked it (no model, the ceiling reached, or the org's evals used up).
ScoreVerdict: TypeAlias = Literal["held", "broken", "classified", "na", "deferred", "skipped"]

# cold: a REFER on the caller's SIP leg. warm: the number is dialled into the room.
TransferMode: TypeAlias = Literal["cold", "warm"]

PromptRegion: TypeAlias = Literal["static", "dynamic"]
DocsMode: TypeAlias = Literal["retrieved", "tool"]
PlatformTool: TypeAlias = Literal["recall", "search"]
UserState: TypeAlias = Literal["listening", "speaking", "away"]
AgentState: TypeAlias = Literal["initializing", "idle", "listening", "thinking", "speaking"]
ParticipantKind: TypeAlias = Literal["caller", "agent", "supervisor", "listener", "sip"]
TrackKind: TypeAlias = Literal["audio", "video", "screen"]
TrackSource: TypeAlias = Literal[
    "microphone", "camera", "screen_share", "screen_share_audio", "unknown"
]
Visibility: TypeAlias = Literal["public", "tenant", "pii"]

# Which projection a sink applies before a state or an entry leaves the platform.
Projection: TypeAlias = Literal["public", "tenant"]

CallStatus: TypeAlias = Literal["idle", "ringing", "dialing", "active", "ended"]
SessionFlag: TypeAlias = Literal["escalated", "low_score", "promise"]
ThreadKind: TypeAlias = Literal["in", "out", "call"]
WidgetTheme: TypeAlias = Literal["auto", "light", "dark"]


# The provider of the box's own rows (its compute): what the platform cost, beside the vendors'.
PLATFORM = "pinecall"


class PromptBlockSpec(WireModel):
    """One named block of the prompt and the region it lives in."""

    name: str = Field(pattern="^[a-z][a-z0-9_]*$")
    region: PromptRegion


class Contact(WireModel):
    """Who is on the line, as far as the platform knows; a web visitor may be nobody yet."""

    id: str | None = None
    phone: str | None = None
    name: str | None = None
    email: str | None = None
    external_id: str | None = None


class Route(WireModel):
    """One door to an agent: a channel and, for phone and WhatsApp, the number that answers."""

    channel: Channel
    number: str | None
    label: str | None = None


class Supervisor(WireModel):
    """The human who sent a supervise verb, as the token that let them in names them."""

    id: str
    name: str | None = None


class ToolSpec(WireModel):
    """What the app declares about one tool."""

    name: str
    description: str
    parameters: JsonObject
    side_effect: Literal["read", "write", "irreversible"] = "read"
    confirm: str | None = None
    announce: str | None = None
    pii: list[str] | None = None
    timeout_s: float | None = None


class ToolResult(WireModel):
    """What came back from running a tool in the app's process: an output or an error."""

    call_id: str
    name: str
    output: Json = None
    error: str | None = None
    summary: str | None = None
    duration_s: float | None = None


class StateCauseTool(WireModel):
    """A tool call's result changed the state: the tool's method wrote the field while it ran."""

    kind: Literal["tool"] = "tool"
    tool: str
    call_id: str


class StateCauseEvent(WireModel):
    """A fact from outside changed the state: the app's handler for an event wrote the field."""

    kind: Literal["event"] = "event"
    name: str
    seq: int


class StateCauseHook(WireModel):
    """A lifecycle hook changed the state: the one that ran when the call started, or on memory."""

    kind: Literal["hook"] = "hook"
    hook: Literal["on_call", "on_memory"]


StateCause: TypeAlias = Annotated[
    StateCauseTool | StateCauseEvent | StateCauseHook, Field(discriminator="kind")
]

# The tool the platform puts in front of a model that may hang up; its tool.call and tool.result
# are both the platform's, so an app answers none.
END_CALL = "end_call"


class MemoryFact(WireModel):
    """One thing remembered about a contact."""

    id: str | None = None
    text: str
    category: str | None = None
    score: float | None = None
    source: str | None = None


class MemoryOp(WireModel):
    """One operation against the contact's memory."""

    op: Literal["recall", "remember", "forget"]
    contact: str | None = None
    query: str | None = None
    facts: list[MemoryFact]
    took_ms: float


class DocSource(WireModel):
    """One chunk of the knowledge base that retrieval put in front of the model for this turn."""

    id: str
    base: str | None = None
    path: str
    heading: str | None = None
    score: float
    excerpt: str | None = None


class CostRow(WireModel):
    """One priced line: a model, what was counted, how much, and what it came to."""

    provider: str
    model: str
    unit: Literal[
        "input_tokens",
        "cached_input_tokens",
        "cache_creation_tokens",
        "output_tokens",
        "characters",
        "audio_seconds",
        "requests",
        "session_seconds",
        "minutes",
    ]
    quantity: float
    unit_price_usd: float
    # A summary written before money in dollars priced its rows in euros: the same number, read as
    # dollars and never converted, as migration 0007 kept the facts' column.
    usd: float = Field(validation_alias=AliasChoices("usd", "eur"))


class UnpricedRow(WireModel):
    """A usage row the price table does not know: listed, never priced at zero."""

    provider: str
    model: str


class Cost(WireModel):
    """What the call cost in provider fees and, priced, the box's own compute; US dollars."""

    usd: float = Field(validation_alias=AliasChoices("usd", "eur"))
    rows: list[CostRow]
    unpriced: list[UnpricedRow]
    # The euro's rate a summary written before money in dollars carried; read, never written.
    rate: JsonObject | None = Field(default=None, exclude=True)
