"""What an app declares about its agent, whole: its stages, its words, its judges and personas, what it watches."""

from typing import Any, Self

from pydantic import Field, model_validator

from runtime.enums import JudgeAnswer, JudgeRunsWhen, MonitorMetric
from runtime.kit.text import Json, JsonObject
from runtime.wire.base import WireModel
from runtime.wire.parts import (
    Ambience,
    DocsMode,
    EndOfTurn,
    EventSource,
    JudgeRead,
    PromptBlockSpec,
    ToolSpec,
    Visibility,
    WidgetTheme,
)

# What an idle line waits and how many are said, when the agent does not say.
IDLE_AFTER_S = 7.5
IDLE_TIMES = 3
# The metrics that are a share of the calls, so their line sits between 0 and 1.
RATES = frozenset({MonitorMetric.held_rate, MonitorMetric.escalated_rate, MonitorMetric.tool_failure_rate})
# The windows a monitor reads its number over, in days.
WINDOWS = frozenset({1, 7, 30})


class IdleConfig(WireModel):
    """What the agent says when the caller has gone quiet."""

    says: list[str]
    after_s: float = IDLE_AFTER_S
    times: int = IDLE_TIMES


class VoicemailConfig(WireModel):
    """Lets the model tell a machine from a person on a call it placed, and what it leaves there."""

    message: str | None = None


class MonitorDeclared(WireModel):
    """One number of the agent's calls the class watches: it fires, once a day, when it crosses the line."""

    name: str = Field(min_length=1)
    metric: MonitorMetric
    above: bool
    threshold: float
    window_days: int = 7

    @model_validator(mode="after")
    def _a_share(self) -> Self:
        if self.window_days not in WINDOWS:
            raise ValueError(f"window_days is one of {sorted(WINDOWS)}, not {self.window_days}")
        if self.metric in RATES and not 0 <= self.threshold <= 1:
            raise ValueError(f"{self.metric} is a share between 0 and 1, not {self.threshold}")
        return self


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
    """One judge of the agent's own, as its class declares it: an `ownJudge` in its code."""

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
    """One caller of the agent's own, as its class declares it: an `ownPersona` in its code."""

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
    timezone: str | None = None
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
    # Several bases: `docs` said for more than one, and never beside it.
    bases: list[DocsConfig] | None = None
    memory: MemoryConfig | None = None
    hangup: HangupConfig | None = None
    # Sent as null, a setting is the org's settings' again; `uses_knowledge` null is false.
    record: bool | None = True
    # The longest a voice call runs, in seconds (0 for no limit), and how long a turn waits for the model's first word.
    max_duration_s: int | None = None
    llm_timeout_s: float | None = None
    # Seconds of a caller saying nothing before the call ends; what it says first; and on a call it placed, a machine.
    silence_timeout_s: int | None = None
    idle: IdleConfig | None = None
    voicemail: VoicemailConfig | None = None
    # The vendors that take over a stage, `vendor` or `vendor/model`, in order.
    stt_fallbacks: list[str] | None = None
    tts_fallbacks: list[str] | None = None
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
    # The numbers of its calls the class watches: its monitors, kept as it declares them.
    monitors: list[MonitorDeclared] | None = None
