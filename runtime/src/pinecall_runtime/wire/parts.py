"""The parts events, commands and state share: the wire's words and its common shapes."""

from typing import Annotated, Any, Literal

from pydantic import AliasChoices, Field

from pinecall_runtime.enums import Channel, JudgeAnswer, JudgeRunsWhen
from pinecall_runtime.kit.text import Json, JsonObject
from pinecall_runtime.wire.base import WireModel

type DevVerb = Literal[
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
type EndReason = Literal[
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
# The quotas an org is counted against; `credits.exhausted` names the one that ran out.
type QuotaName = Literal[
    "minutes",
    "messages",
    "agents",
    "concurrent_calls",
    "memory_facts",
    "knowledge_chunks",
    "numbers",
    "seats",
    "llm_tokens",
    "hosted_apps",
    "evals",
    "simulations",
    "budget_usd",
]


type EndedBy = Literal["caller", "agent", "supervisor", "platform"]
type ScoreVerdict = Literal["held", "broken", "classified", "na", "deferred", "skipped"]
type TransferMode = Literal["cold", "warm"]
type PromptRegion = Literal["static", "dynamic"]
type DocsMode = Literal["retrieved", "tool"]
type PlatformTool = Literal["recall", "search"]
type UserState = Literal["listening", "speaking", "away"]
type AgentState = Literal["initializing", "idle", "listening", "thinking", "speaking"]
type ParticipantKind = Literal["caller", "agent", "supervisor", "listener", "sip"]
type TrackKind = Literal["audio", "video", "screen"]
type TrackSource = Literal["microphone", "camera", "screen_share", "screen_share_audio", "unknown"]
type Visibility = Literal["public", "tenant", "pii"]
# What a `pii` value reads as wherever the log holds it (`docs/protocol/projections.md`).
MASKED = "***"
type Projection = Literal["public", "tenant"]
type CallStatus = Literal["idle", "ringing", "dialing", "active", "ended"]
type SessionFlag = Literal["escalated", "low_score", "promise"]
type ThreadKind = Literal["in", "out", "call"]
type WidgetTheme = Literal["auto", "light", "dark"]
type EventSource = Literal["app", "participant"]
type SideEffect = Literal["read", "write", "irreversible"]
type EndOfTurn = Literal["stt", "livekit", "smart-turn"]
# What plays behind a simulated caller once `interferer_db` names a level.
type Ambience = Literal["television", "cafe", "office", "street"]
# The call and its tool calls are always read; each of these adds a block to a judge's question.
type JudgeRead = Literal["prompt", "evidence", "facts"]
type CostUnit = Literal[
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

# The provider of the box's own cost rows: what the platform cost, beside the vendors'.
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
    """One way to an agent: a channel and, for phone and WhatsApp, the number that answers."""

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
    parameters: dict[str, Any]
    side_effect: SideEffect = "read"
    confirm: str | None = None
    announce: str | None = None
    pii: list[str] | None = None
    timeout_s: float | None = None
    # A move on the caller's screen, such as a pointer: it runs as the model calls it, while the
    # words of that answer still play, and asks the model for no answer of its own.
    quiet: bool | None = None


class ToolResult(WireModel):
    """What came back from running a tool in the app's process."""

    call_id: str
    name: str
    output: Json = None
    error: str | None = None
    summary: str | None = None
    duration_s: float | None = None


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


class StateCauseHook(WireModel):
    """A lifecycle hook of the app changed the state."""

    kind: Literal["hook"] = "hook"
    hook: Literal["on_call", "on_memory"]


type StateCause = Annotated[StateCauseTool | StateCauseEvent | StateCauseHook, Field(discriminator="kind")]


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
    """One chunk of the knowledge base retrieval put in front of the model for a turn."""

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
    unit: CostUnit
    quantity: float
    unit_price_usd: float
    # Summaries written before money in dollars said `eur`: the same number, read as dollars.
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
    rate: dict[str, Any] | None = Field(default=None, exclude=True)


class VoiceConfig(WireModel):
    """Which voice speaks for the agent."""

    name: str | None = None
    provider: str | None = None
    model: str | None = None
    voice_id: str | None = None
    builds: str | None = None
    options: dict[str, Any] | None = None


class ModelConfig(WireModel):
    """Which model does a job (the LLM, or the STT), and the knobs worth turning."""

    provider: str
    model: str
    temperature: float | None = None
    builds: str | None = None
    options: dict[str, Any] | None = None
    end_of_turn: EndOfTurn | None = None


class TurnConfig(WireModel):
    """How the session decides the caller has finished, and when they may interrupt."""

    min_interruption_words: int | None = None
    endpointing_ms: int | None = None
    eot_threshold: float | None = None
    eager_eot_threshold: float | None = None
    min_interruption_ms: int | None = None


class Pronunciation(WireModel):
    """How the voice says one word it would otherwise get wrong."""

    word: str
    spoken: str


class StateFieldSpec(WireModel):
    """What the app declares about one field of its state: who may see it."""

    name: str
    visibility: Visibility


class ViewSpec(WireModel):
    """The panel the agent draws beside a conversation."""

    name: str


class EventSpec(WireModel):
    """One outside event the agent accepts, and from whom."""

    name: str
    from_: list[EventSource] = Field(alias="from")


class KnowledgeFile(WireModel):
    """One file of a base, as a push sends it."""

    path: str
    text: str


class DocsConfig(WireModel):
    """The knowledge base the agent answers from, and how its chunks reach the model."""

    base: str
    mode: DocsMode = "retrieved"
    k: int = 8
    min_score: float | None = None


class GreetingConfig(WireModel):
    """How the agent opens a call: `say` the words, or `reply` what the model reads first."""

    say: str | None = None
    reply: str | None = None
    allow_interruptions: bool | None = None


class HangupConfig(WireModel):
    """Whether the model may end the call itself, and when."""

    when: str = ""


class MemoryConfig(WireModel):
    """What memory keeps about a contact across calls, and what it must never keep."""

    remember: list[str] = Field(default_factory=list[str])
    forget: list[str] = Field(default_factory=list[str])


class JudgeDeclaration(WireModel):
    """One judge of the agent's own, as its class declares it: `judges/<name>.md` read."""

    name: str
    question: str
    answer: JudgeAnswer = JudgeAnswer.verdict
    # The answers a `choice` judge picks from: two at least, and only for `choice`.
    choices: list[str] = Field(default_factory=list[str])
    when: JudgeRunsWhen = JudgeRunsWhen.always
    trigger: str = ""
    reads: list[JudgeRead] = Field(default_factory=list[JudgeRead])


class JudgesDeclared(WireModel):
    """The judges the class owns: which of Pinecall's its calls meet, and its own."""

    on: list[str] = Field(default_factory=list[str])
    own: list[JudgeDeclaration] = Field(default_factory=list[JudgeDeclaration])


class CallerBehavior(WireModel):
    """How a simulated caller acts on a spoken line, beside what it says."""

    # The share of the agent's answers the caller talks over once the agent has started, 0 to 1.
    interrupts: float = Field(default=0.0, ge=0.0, le=1.0)
    # Seconds of silence before each line.
    pause_s: float = Field(default=0.0, ge=0.0, le=10.0)
    # The ambience under the caller's voice, this many dB below it; null: a quiet room.
    interferer_db: float | None = None
    packet_loss: float = Field(default=0.0, ge=0.0, le=0.5)
    # The share of the agent's answers the caller murmurs an "mm-hmm" into without taking its turn.
    backchannels: float = Field(default=0.0, ge=0.0, le=1.0)
    # How fast the caller speaks: 1 as the vendor reads it, 0.5 half as fast, 2 twice.
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    ambience: Ambience = "television"


class PersonaDeclaration(WireModel):
    """One caller of the agent's own, as its class declares it: `test/personas/<name>.json` read."""

    name: str
    goal: str
    style: str
    about: str = ""
    facts: dict[str, str] = Field(default_factory=dict[str, str])
    state: JsonObject = Field(default_factory=dict[str, Json])
    # One verifiable demand a line ("The agent should…"); the expected-outcome judge reads them.
    expects: list[str] = Field(default_factory=list[str])
    tags: list[str] = Field(default_factory=list[str])
    behavior: CallerBehavior = Field(default_factory=CallerBehavior)
    # The vendors the caller is played on; null is the runtime's.
    llm: str | None = None
    tts: str | None = None
    voice: str | None = None


class PersonasDeclared(WireModel):
    """The personas the class owns: which of Pinecall's its runs play, and its own."""

    on: list[str] = Field(default_factory=list[str])
    own: list[PersonaDeclaration] = Field(default_factory=list[PersonaDeclaration])


class HoldConfig(WireModel):
    """The hold melody as the class declares it: the file it ships (by hash), the wait before it, or silence."""

    # The sha256 of the file the class plays, as shipped: the class's process uploads it, and nobody else may.
    clip: str | None = None
    name: str | None = None
    # Seconds of the agent's quiet before the melody starts; null is the runtime's own wait.
    after_s: float | None = None
    # True plays nothing while a tool runs.
    off: bool = False


class WidgetLook(WireModel):
    """How the widget presents the agent, as the class declares it; a null field is the widget's own default."""

    title: str | None = None
    tagline: str | None = None
    greeting: str | None = None
    accent: str | None = None
    autostart: bool = False
    theme: WidgetTheme | None = None


class AgentConfig(WireModel):
    """What an app declares about its agent; every field optional so a configure changes one thing."""

    prompt: list[PromptBlockSpec] | None = None
    language: str | None = None
    greeting: GreetingConfig | None = None
    voice: VoiceConfig | None = None
    llm: ModelConfig | None = None
    # The model a voice call runs on alone, hearing and speaking itself; a written call runs on `llm`.
    realtime: ModelConfig | None = None
    stt: ModelConfig | None = None
    judge: ModelConfig | None = None
    turn: TurnConfig | None = None
    says: list[Pronunciation] | None = None
    hears: list[str] | None = None
    knowledge: KnowledgeFile | None = None
    docs: DocsConfig | None = None
    memory: MemoryConfig | None = None
    hangup: HangupConfig | None = None
    # Sent as null, a setting is the org's settings' again; `uses_knowledge` null is false.
    record: bool | None = True
    # The longest a voice call runs, in seconds (0 for no limit), and how long a turn waits for the model's first word.
    max_duration_s: int | None = None
    llm_timeout_s: float | None = None
    tools: list[ToolSpec] | None = None
    uses_knowledge: bool | None = False
    state_fields: list[StateFieldSpec] | None = None
    view: ViewSpec | None = None
    events: list[EventSpec] | None = None
    # Declared, the class owns the agent's judges and its personas: nothing of either is written in the console.
    judges: JudgesDeclared | None = None
    personas: PersonasDeclared | None = None
    # Declared, the class owns the hold melody and the widget's look: the pipeline and widget doors refuse a write.
    hold: HoldConfig | None = None
    widget: WidgetLook | None = None
