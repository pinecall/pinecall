"""What a class declares of its environment, as the wire carries it: settings, judges, look."""

from pydantic import Field

from pinecall.wire._names import EventSource, JsonObject
from pinecall.wire.frames import WireModel
from pinecall.wire.judging import JudgesDeclared, PersonasDeclared
from pinecall.wire.parts import (
    DocsMode,
    EndOfTurn,
    PromptBlockSpec,
    ToolSpec,
    Visibility,
    WidgetTheme,
)


class VoiceConfig(WireModel):
    """Which voice speaks for the agent."""

    name: str | None = None
    provider: str | None = None
    model: str | None = None
    voice_id: str | None = None
    # A class of the vendor's livekit plugin other than its TTS, and its keyword arguments as the
    # plugin names them: what a class declares, over the operator's options for the vendor.
    builds: str | None = None
    options: JsonObject | None = None


class ModelConfig(WireModel):
    """Which model does a job (the LLM, or the STT), and the one or two knobs worth turning."""

    provider: str
    model: str
    temperature: float | None = None
    # A class of the vendor's livekit plugin other than its LLM or STT (`responses.LLM`), and its
    # keyword arguments as the plugin names them: what a class declares, over the operator's.
    builds: str | None = None
    options: JsonObject | None = None
    # The ears' alone: who ends the caller's turn, over the operator's choice for the vendor.
    end_of_turn: EndOfTurn | None = None


class TurnConfig(WireModel):
    """How the session decides that the caller has finished, and when the caller may interrupt."""

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
    """The panel the agent draws beside a conversation; its contents come by dev verb."""

    name: str


class EventSpec(WireModel):
    """One outside event the agent accepts, and from whom."""

    name: str
    from_: list[EventSource] = Field(alias="from")


class KnowledgeFile(WireModel):
    """One file of a base, as a push sends it: its path as the tenant keeps it, and its text."""

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


class HoldConfig(WireModel):
    """The hold melody as the class declares it: the file it ships by hash, the wait, or silence."""

    clip: str | None = None
    name: str | None = None
    after_s: float | None = None
    off: bool = False


class WidgetLook(WireModel):
    """How the widget presents the agent, as the class declares it; a null field is the default."""

    title: str | None = None
    tagline: str | None = None
    greeting: str | None = None
    accent: str | None = None
    autostart: bool = False
    theme: WidgetTheme | None = None


# Every field is optional so a configure can change one thing.
class AgentConfig(WireModel):
    """What an app declares about its agent."""

    prompt: list[PromptBlockSpec] | None = None
    language: str | None = None
    greeting: GreetingConfig | None = None
    voice: VoiceConfig | None = None
    llm: ModelConfig | None = None
    # The model a voice call runs on alone, hearing and speaking itself; a written call, on `llm`.
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
    record: bool = True
    # The longest a voice call runs, in seconds (0: no limit); how long a turn waits for the model.
    max_duration_s: int | None = None
    llm_timeout_s: float | None = None
    tools: list[ToolSpec] | None = None
    uses_knowledge: bool = False
    state_fields: list[StateFieldSpec] | None = None
    view: ViewSpec | None = None
    events: list[EventSpec] | None = None
    # Declared, the class owns the agent's judges and its personas: no door writes either.
    judges: JudgesDeclared | None = None
    personas: PersonasDeclared | None = None
    # Declared, the class owns the hold melody and the widget's look.
    hold: HoldConfig | None = None
    widget: WidgetLook | None = None
