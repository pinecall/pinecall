"""The bodies of the agents endpoints: settings and lexicon versions, canaries, pipeline, widget, apps, the line."""

from typing import Any, Literal, Self

from pydantic import Field

from pinecall_runtime.agents.declaration import Modality
from pinecall_runtime.agents.models import HoldAudio as HoldAudioRow
from pinecall_runtime.enums import Channel, Env, HoldPlayed
from pinecall_runtime.kit.schemas import Schema
from pinecall_runtime.providers.schemas import ProviderRow
from pinecall_runtime.wire.base import WireModel
from pinecall_runtime.wire.parts import (
    DocsConfig,
    EndOfTurn,
    GreetingConfig,
    HangupConfig,
    MemoryConfig,
    ModelConfig,
    Pronunciation,
    TurnConfig,
    WidgetTheme,
)

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


class SettingsRow(WireModel):
    """One kept version of an agent's settings: whose scope, which version, by whom, what."""

    holder: str
    version: int
    author: str
    note: str | None
    set_at: float
    config: SettingsBody


class SettingsResponse(WireModel):
    """GET /v1/agents/{slug}/settings: yours, the team's and production's newest, or null."""

    world: Env
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


class SettingsHistoryResponse(WireModel):
    """GET /v1/agents/{slug}/settings/history: one scope's versions, newest first."""

    world: Env
    holder: str
    rows: list[SettingsRow]


class SettingsDiffResponse(WireModel):
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


class CanaryRow(WireModel):
    """The canary a scope stands on: which version takes how many calls in a hundred, by whom."""

    holder: str
    version: int
    share: int
    author: str
    note: str | None
    set_at: float


class CanaryResponse(WireModel):
    """GET, PUT and DELETE /v1/agents/{slug}/settings/canary: the scope's canary, or null."""

    world: Env
    holder: str
    canary: CanaryRow | None


class LexiconBody(WireModel):
    """The agent's lexicon: how the voice says its words, and the words the ears must know."""

    said: list[Pronunciation]
    heard: list[str]


class LexiconRow(WireModel):
    """One kept version of the agent's lexicon."""

    holder: str
    version: int
    author: str
    note: str | None
    set_at: float
    lexicon: LexiconBody


class LexiconResponse(WireModel):
    """GET /v1/agents/{slug}/lexicon: yours, the team's and production's newest, or null."""

    world: Env
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


class LexiconHistoryResponse(WireModel):
    """GET /v1/agents/{slug}/lexicon/history: one scope's versions, newest first."""

    world: Env
    holder: str
    rows: list[LexiconRow]


class CallSettingsResponse(WireModel):
    """GET /v1/calls/{call}/settings: the tuning and lexicon the call was built on."""

    config_version: int | None
    lexicon_version: int | None
    config: SettingsRow | None
    lexicon: LexiconRow | None
    # The call ran a canary's version, picked for its share of the calls.
    canary: bool = False


# ── the agents an org holds, its apps, and whose terminal a ring lands in ──


class ScopeHolder(WireModel):
    """A scope by its member id and email; both null for the org's own."""

    holder: str | None
    name: str | None


class AgentRow(WireModel):
    """An agent some socket of the org holds, the channels it answers, and whose scope."""

    slug: str
    channels: list[Channel]
    holder: ScopeHolder | None = None


class AgentList(WireModel):
    """The org's held agents in the request's env."""

    agents: list[AgentRow]


class AppRow(WireModel):
    """One connected app socket and what it holds."""

    app: str
    agents: list[str]
    env: Env
    host: str | None
    address: str | None
    sdk: str | None
    holder: ScopeHolder | None
    connected_at: float


class AppList(WireModel):
    """The app sockets of the org this key may see."""

    apps: list[AppRow]


class StopAppResponse(WireModel):
    """A stop answered."""

    app: str
    stopped: bool


class KilledAgent(WireModel):
    """An agent killed: the envs it was held in, and the app sockets that let go of it."""

    agent: str
    envs: list[Env]
    apps: list[str]


class RingTarget(WireModel):
    """Whose terminal a ring at the agent lands in, and who else could take it."""

    agent: str
    env: Env
    held: bool
    holding: ScopeHolder | None = None
    yours: bool
    waiting: list[ScopeHolder]
    calling: list[str]


class DeveloperPhone(WireModel):
    """The phone a developer calls from."""

    number: str


class TestNumber(WireModel):
    """A production number and the agent it reaches."""

    number: str
    agent: str


class TestNumbers(WireModel):
    """The person's own phones, and the production numbers they can dial to test."""

    calling: list[str]
    numbers: list[TestNumber]


class JudgingSettings(WireModel):
    """Whether an org's calls are judged at hang-up, on what model, and the ceiling per call."""

    on: bool
    ceiling_usd: float | None
    # The model the org's calls are judged on, an agent's own over it; null: the platform's.
    model: ModelConfig | None = None


class JudgingRequest(WireModel):
    """PUT /v1/org/judging, whole: on or off, and the model; a model left out is the platform's."""

    on: bool
    model: ModelConfig | None = None


# ── the pipeline, the hold melody, the widget ──


class HoldAudio(WireModel):
    """What a caller hears while a tool runs: the box's melody, silence, or the org's own clip."""

    played: HoldPlayed | Literal["default"]
    sha256: str | None = None
    seconds: float | None = None
    name: str | None = None

    @classmethod
    def of(cls, row: HoldAudioRow | None) -> Self:
        """What the agent plays, from its row; the default when it has none."""
        if row is None:
            return cls(played="default")
        return cls(played=row.played, sha256=row.sha256, seconds=row.seconds, name=row.name)


class PlayedRequest(WireModel):
    """PUT /v1/agents/{slug}/pipeline/hold-audio/played: the box's melody back, or silence."""

    played: Literal["default", "off"]


class PipelineStage(WireModel):
    """One stage as the next call would run it: the vendor, its model, the voice or language."""

    vendor: str
    model: str | None = None
    voice_id: str | None = None
    language: str | None = None


class Measured(WireModel):
    """One latency over the agent's recent calls: livekit's name, the median, the turns."""

    name: str
    seconds: float
    turns: int


class PipelineReport(WireModel):
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
    defaults: dict[Modality, str]
    models: dict[str, list[str]]
    # By stage and vendor, the model a call runs when none is picked, as GET /v1/providers says it.
    runs: dict[str, str]
    # By vendor, the models that hear and speak themselves, as GET /v1/providers lists them.
    realtime: dict[str, list[str]]
    calls: int
    medians: list[Measured]
    unavailable_reasons: dict[str, str]


class RunningStage(WireModel):
    """One stage as the worker builds it: the vendor, its key, and what the plugin is told."""

    vendor: str
    credentials: str | dict[str, Any]
    model: str | None = None
    builds: str | None = None
    options: dict[str, Any] = Field(default_factory=dict[str, Any])
    voice: str | None = None
    language: str | None = None
    hints: list[str] = Field(default_factory=list[str])
    ends_the_turn: bool = False
    turn_model: Literal["v1-mini", "smart-turn-v3"] = "smart-turn-v3"
    request: dict[str, Any] = Field(default_factory=dict[str, Any])
    lent: bool = False
    fallbacks: list["RunningStage"] = Field(default_factory=list["RunningStage"])


class TelemetryTarget(WireModel):
    """The org's own collector, headers opened, for the worker to export the call's spans to."""

    endpoint: str
    headers: dict[str, str] = Field(default_factory=dict[str, str])
    pii: bool = False


class PipelineKeys(WireModel):
    """GET /v1/agents/{slug}/provider-keys: the stages on their keys, and where traces go."""

    llm: RunningStage
    stt: RunningStage
    tts: RunningStage
    # A voice call's whole conversation, where the agent names a model that hears and speaks itself.
    # Sent only then, so a worker of the version before reads every other answer as it did.
    realtime: RunningStage | None = None
    telemetry: TelemetryTarget | None = None


class WidgetSettings(WireModel):
    """GET and PUT /v1/agents/{slug}/widget: how the widget presents the agent, per env."""

    title: str | None = None
    tagline: str | None = None
    greeting: str | None = None
    accent: str | None = None
    autostart: bool = False
    theme: WidgetTheme | None = None


class MoveAgentRequest(Schema):
    """PUT /v1/ops/orgs/{named}/agents: the agent to move into this org."""

    agent: str


class AgentMoved(WireModel):
    """The move: how many logs came, which numbers came, which stayed where they were."""

    agent: str
    org: str
    logs: int
    numbers: list[str]
    stayed: list[str]
