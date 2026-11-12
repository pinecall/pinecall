"""The bodies of the agents endpoints: settings and lexicon versions, canaries, the pipeline, the melody, the widget."""

from typing import Annotated, Any, Literal

from pydantic import AliasChoices, Field, field_validator

from runtime.agents.settings import AgentSettings, Lexicon, dump_settings
from runtime.enums import Env, Stage
from runtime.kit.schemas import Epoch, Row, Schema
from runtime.providers.schemas import ModelChoice, ProviderRow
from runtime.wire.base import WireModel
from runtime.wire.declared import (
    DocsConfig,
    GreetingConfig,
    HangupConfig,
    IdleConfig,
    MemoryConfig,
    Pronunciation,
    TurnConfig,
    VoicemailConfig,
)
from runtime.wire.parts import EndOfTurn, WidgetTheme

# The console and the CLI read an env as `world` off these answers; in here it is `env`, read by either name.
AN_ENV = AliasChoices("env", "world")

# ── settings ──


# Every field is optional: one left out is not set, and the runtime's own default stands for it.
class SettingsBody(WireModel):
    """An agent's settings as the org set them, per env and per scope."""

    voice: str | None = None
    tts: str | None = None
    tts_model: str | None = None
    stt: str | None = None
    llm: str | None = None
    language: str | None = None
    timezone: str | None = None
    greeting: GreetingConfig | None = None
    hangup: HangupConfig | None = None
    turn: TurnConfig | None = None
    memory: MemoryConfig | None = None
    record: bool | None = None
    max_duration_s: int | None = None
    llm_timeout_s: float | None = None
    temperature: float | None = None
    end_of_turn: EndOfTurn | None = None
    # Each stage's plugin class and its keyword arguments, the org's own key alone running them.
    tts_builds: str | None = None
    tts_options: dict[str, Any] | None = None
    stt_builds: str | None = None
    stt_options: dict[str, Any] | None = None
    llm_builds: str | None = None
    llm_options: dict[str, Any] | None = None
    # The model a voice call runs on alone, `vendor/model`, hearing and speaking itself; its options
    # run on the org's own key. A written call runs on `llm`.
    realtime: str | None = None
    realtime_options: dict[str, Any] | None = None
    # The model the agent's calls are judged on, `vendor/model`; null is the org's choice.
    judge: str | None = None
    judge_builds: str | None = None
    judge_options: dict[str, Any] | None = None
    knowledge: str | None = None
    bases: list[DocsConfig] | None = None
    # Seconds of a caller saying nothing before the call ends; unset never ends it for that.
    silence_timeout_s: int | None = None
    idle: IdleConfig | None = None
    voicemail: VoicemailConfig | None = None
    # The vendors that take over a stage, `vendor` or `vendor/model`, in order: over the row's own.
    stt_fallbacks: list[str] | None = None
    tts_fallbacks: list[str] | None = None


# A field nobody set is left out of the answer, never sent as null: the kept settings are read as they
# are kept, each field set by its name, so the answer says exactly the fields the row holds.
class SettingsRow(Row):
    """One kept version of an agent's settings: whose scope, which version, by whom, what."""

    holder: str
    version: int
    author: str
    note: str | None
    set_at: Epoch
    config: SettingsBody = Field(validation_alias=AliasChoices("value", "config"))

    @field_validator("config", mode="before")
    @classmethod
    def _read_as_kept(cls, value: object) -> object:
        return dump_settings(value) if isinstance(value, AgentSettings) else value


class SettingsResponse(Row):
    """GET /v1/agents/{slug}/settings: yours, the team's and production's newest, or null."""

    world: Env = Field(validation_alias=AN_ENV)
    yours: SettingsRow | None
    team: SettingsRow | None
    production: SettingsRow | None
    # The settings the class holding the agent declares itself, by the declaration's names
    # (`voice`, `llm`, `docs`…): each wins over these, which may not change it while it does.
    fixed: list[str] = Field(default_factory=list[str])


class PutSettingsRequest(WireModel):
    """PUT /v1/agents/{slug}/settings: the whole set, the version read, why, whose scope."""

    config: SettingsBody
    if_version: int | None = None
    note: str | None = None
    team: bool = False


class HistoryQuery(Schema):
    """The query string of a history: whose scope, and how many versions at most."""

    team: bool = False
    limit: int = Field(default=20, ge=1, le=200)


class SettingsHistoryResponse(Row):
    """GET /v1/agents/{slug}/settings/history: one scope's versions, newest first."""

    world: Env = Field(validation_alias=AN_ENV)
    holder: str
    rows: list[SettingsRow]


class SettingsDiffResponse(Row):
    """GET /v1/agents/{slug}/settings/diff: this scope's newest against another's, by field."""

    ours: SettingsRow | None
    theirs: SettingsRow | None
    changed: list[str]


class RollbackSettingsRequest(WireModel):
    """POST /v1/agents/{slug}/settings/rollback: the version to bring back, as a new one."""

    version: int
    team: bool = False


# A share is whole percents: 0 keeps the version off every call without clearing the canary.
class PutCanaryRequest(WireModel):
    """PUT /v1/agents/{slug}/settings/canary: the version, its share of the calls, why, whose."""

    version: int = Field(ge=1)
    share: int = Field(ge=0, le=100)
    note: str | None = None
    team: bool = False


class CanaryQuery(Schema):
    """The query string of a canary's read or clearing: whose scope."""

    team: bool = False


class CanaryRow(Row):
    """The canary a scope stands on: which version takes how many calls in a hundred, by whom."""

    holder: str
    version: int
    share: int
    author: str
    note: str | None
    set_at: Epoch


class CanaryResponse(Row):
    """GET, PUT and DELETE /v1/agents/{slug}/settings/canary: the scope's canary, or null."""

    world: Env = Field(validation_alias=AN_ENV)
    holder: str
    canary: CanaryRow | None


# ── the lexicon ──


class LexiconBody(WireModel):
    """The agent's lexicon: how the voice says its words, and the words the ears must know."""

    said: list[Pronunciation]
    heard: list[str]


class LexiconRow(Row):
    """One kept version of the agent's lexicon."""

    holder: str
    version: int
    author: str
    note: str | None
    set_at: Epoch
    lexicon: LexiconBody = Field(validation_alias=AliasChoices("value", "lexicon"))

    @field_validator("lexicon", mode="before")
    @classmethod
    def _read_as_listed(cls, value: object) -> object:
        if not isinstance(value, Lexicon):
            return value
        said = [{"word": word, "spoken": spoken} for word, spoken in value.said.items()]
        return {"said": said, "heard": list(value.heard)}


class LexiconResponse(Row):
    """GET /v1/agents/{slug}/lexicon: yours, the team's and production's newest, or null."""

    world: Env = Field(validation_alias=AN_ENV)
    yours: LexiconRow | None
    team: LexiconRow | None
    production: LexiconRow | None
    # Which of `says` and `hears` the class holding the agent declares itself: it wins over these.
    fixed: list[str] = Field(default_factory=list[str])


class PutLexiconRequest(WireModel):
    """PUT /v1/agents/{slug}/lexicon: the whole lexicon, the version read, why, whose scope."""

    lexicon: LexiconBody
    if_version: int | None = None
    note: str | None = None
    team: bool = False


class LexiconHistoryResponse(Row):
    """GET /v1/agents/{slug}/lexicon/history: one scope's versions, newest first."""

    world: Env = Field(validation_alias=AN_ENV)
    holder: str
    rows: list[LexiconRow]


class CallSettingsResponse(Row):
    """GET /v1/calls/{call}/settings: the settings and lexicon the call was built on."""

    config_version: int | None = Field(validation_alias=AliasChoices("settings_version", "config_version"))
    lexicon_version: int | None
    config: SettingsRow | None = Field(validation_alias=AliasChoices("settings", "config"))
    lexicon: LexiconRow | None
    # The call ran a canary's version, picked for its share of the calls.
    canary: bool = False


# ── the pipeline, the hold melody, the widget ──


class PlayedRequest(WireModel):
    """PUT /v1/agents/{slug}/pipeline/hold-audio/played: the runtime's melody back, or silence."""

    played: Literal["default", "off"]


class AfterRequest(WireModel):
    """PUT /v1/agents/{slug}/pipeline/hold-audio/after: seconds of quiet before the melody; null is the runtime's."""

    after_s: float | None


class PipelineStage(Row):
    """One stage as the next call would run it: the vendor, its model, the voice or language."""

    vendor: str
    model: str | None = None
    voice_id: str | None = None
    language: str | None = None


class Measured(Row):
    """One latency over the agent's recent calls: livekit's name, the median, the turns."""

    name: str
    seconds: float
    turns: int


class PipelineReport(Row):
    """GET /v1/agents/{slug}/pipeline: what it hears, decides and speaks with, and how fast."""

    agent: str
    hears: PipelineStage
    decides: PipelineStage
    speaks: PipelineStage
    # What a voice call runs on alone, where the agent names a model that hears and speaks itself:
    # then its voice calls use neither ears nor voice, and `decides` answers its written calls.
    talks: PipelineStage | None = None
    greeting: GreetingConfig | None
    voices: list[str]
    providers: list[ProviderRow]
    defaults: dict[Stage, str]
    models: dict[str, list[str]]
    # By stage and vendor, every model the row offers with its name, price and whether this org may run it,
    # the recommended first, as GET /v1/providers lists them.
    choices: dict[str, list[ModelChoice]] = Field(default_factory=dict[str, list[ModelChoice]])
    # By stage and vendor, the model a call runs when none is picked, as GET /v1/providers says it.
    runs: dict[str, str]
    # By vendor, the models that hear and speak themselves, as GET /v1/providers lists them.
    realtime: dict[str, list[str]]
    # By vendor and language (`google/en`), the voice a call speaks when none is picked: the row's.
    voice_defaults: dict[str, str] = Field(default_factory=dict[str, str])
    calls: int
    medians: list[Measured]
    unavailable_reasons: dict[str, str]


class WidgetSettings(WireModel):
    """GET and PUT /v1/agents/{slug}/widget: how the widget presents the agent, per env."""

    title: str | None = None
    tagline: str | None = None
    greeting: str | None = None
    accent: str | None = None
    autostart: bool = False
    theme: WidgetTheme | None = None
    # True when the agent's class declares the look: a PUT is refused naming the class.
    fixed: bool = False


# ── recorded lines, an output explained ──


class RecordLinesRequest(WireModel):
    """POST /v1/agents/{slug}/lines: the texts to record in the agent's voice, at most 64 of 600 characters."""

    texts: list[Annotated[str, Field(min_length=1, max_length=600)]] = Field(min_length=1, max_length=64)


class RecordedWord(Row):
    """A written word of a line, and when it is said, in ms from the start of the audio."""

    text: str
    start_ms: int
    end_ms: int


class RecordedLine(Row):
    """A line recorded in the agent's voice: where its MP3 is, how long it runs, when each word is said."""

    id: str
    text: str
    url: str
    duration_ms: int
    voice: str
    # False where the voice times no words and each word was placed by its length.
    timed: bool
    words: list[RecordedWord]


class RecordedLines(Row):
    """The lines asked for, in their order, each recorded once."""

    lines: list[RecordedLine]


class ExplainRequest(WireModel):
    """POST /v1/agents/{slug}/explain: a text a page shows (a command's output), for the agent's model to explain."""

    output: Annotated[str, Field(min_length=1, max_length=8000)]
    command: Annotated[str, Field(max_length=300)] | None = None
    # The language the notes are said in; the agent's when left out.
    language: Annotated[str, Field(min_length=2, max_length=16)] | None = None
    most: Annotated[int, Field(ge=1, le=6)] = 4


class Note(Row):
    """One line of the text, by a fragment copied from it, and what the model says of it."""

    find: str
    say: str


class Explained(Row):
    """The notes the agent's model gave, in the order they are read; none when it found nothing to say."""

    notes: list[Note]
