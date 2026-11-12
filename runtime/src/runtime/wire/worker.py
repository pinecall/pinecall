"""What a worker and the gateway tell each other over HTTP: its heartbeat, and a call's agent, stages and melody."""

from typing import Any, Literal

from pydantic import AliasChoices, Field

from runtime.enums import HoldPlayed
from runtime.wire.base import WireModel
from runtime.wire.declaration import (
    DocsConfig,
    GreetingConfig,
    HangupConfig,
    HoldConfig,
    IdleConfig,
    JudgesDeclared,
    MemoryConfig,
    MonitorDeclared,
    PersonasDeclared,
    TurnConfig,
    VoicemailConfig,
    WidgetLook,
)
from runtime.wire.parts import EndOfTurn, EventSource, PromptRegion, SideEffect, Visibility

# ── the heartbeat ──


class HeartbeatRequest(WireModel):
    """A worker's report: its fleet, its name, what it holds and how loaded it is."""

    fleet: str
    worker: str
    # The name the worker registered under with LiveKit: the one a dispatch reaches it by; null
    # until LiveKit registered it, so no call is offered to a worker nobody can give it to.
    agent_name: str | None = None
    active: int
    # Measured slots; null when the worker is gated on its machine's CPU.
    max_jobs: int | None
    load: float
    draining: bool
    # Its last minute, as its calls' jobs told it; absent from a worker of an older release.
    ended: int | None = None
    failed: int | None = None
    errors: int | None = None
    turns: int | None = None
    first_audio_p95_s: float | None = None


# Both shapes change by addition alone while the release before 2026-11 runs: its workers, draining
# calls for up to an hour, beat to these gateways, and after a rollback these workers beat to its
# gateways; each refuses a field it does not know and requires every one it does.
class HeartbeatResponse(WireModel):
    """The answer to a heartbeat: whether this worker is cordoned, and its fleet full."""

    cordoned: bool
    # No worker ever read it, and the workers of the release before 2026-11 require it: answered
    # until that release is gone, then removed with `slots.accepts_nobody`.
    full: bool


# ── the agent a call runs: GET /v1/agents/{slug}/config ──

# Inside the package a stage's vendor is `vendor`; on this answer it is `provider`, as the release
# before 2026-11 wrote it and its workers read it. The value is read by either name, written by one.
A_VENDOR = AliasChoices("vendor", "provider")


class AgentVoice(WireModel):
    """The voice an agent speaks with: its vendor, and the model, the voice and the plugin's options it names."""

    provider: str = Field(validation_alias=A_VENDOR)
    model: str | None = None
    voice_id: str | None = None
    builds: str | None = None
    options: dict[str, Any] = Field(default_factory=dict[str, Any])


class AgentModel(WireModel):
    """The model an agent thinks, hears or is judged with: its vendor, the model ("" for the vendor's own), options."""

    provider: str = Field(validation_alias=A_VENDOR)
    model: str
    temperature: float | None = None
    builds: str | None = None
    options: dict[str, Any] = Field(default_factory=dict[str, Any])
    end_of_turn: EndOfTurn | None = None


class AgentPromptBlock(WireModel):
    """One named block of the agent's prompt and the region it lives in."""

    name: str
    region: PromptRegion


class AgentTool(WireModel):
    """One tool of the agent as a call runs it: every default the declaration left out filled in."""

    name: str
    description: str
    parameters: dict[str, Any]
    side_effect: SideEffect = "read"
    pii: list[str] = Field(default_factory=list[str])
    confirm: str | None = None
    announce: str | None = None
    delayed: str | None = None
    delayed_after_s: float
    failed: str | None = None
    preview: int | None = None
    timeout_s: float
    quiet: bool = False


# The answer the release before 2026-11 wrote straight off its dataclass, and its workers read back into
# it: every name and type here is that dataclass's, so both releases read each other for the hour they
# run side by side. A field is added, never renamed or removed, until that release is gone.
class AgentConfigResponse(WireModel):
    """GET /v1/agents/{slug}/config: the agent as a call in the scope runs it, its declaration under the settings."""

    slug: str
    # Never set, and never read by a worker: carried until the release that declared it is gone.
    name: str | None = None
    prompt: list[AgentPromptBlock]
    greeting: GreetingConfig | None = None
    language: str | None = None
    timezone: str | None = None
    voice: AgentVoice | None = None
    llm: AgentModel | None = None
    realtime: AgentModel | None = None
    stt: AgentModel | None = None
    judge: AgentModel | None = None
    turn: TurnConfig | None = None
    says: dict[str, str] = Field(default_factory=dict[str, str])
    hears: list[str] = Field(default_factory=list[str])
    knowledge: str | None = None
    bases: list[DocsConfig] = Field(default_factory=list[DocsConfig])
    uses_knowledge: bool = False
    memory: MemoryConfig | None = None
    hangup: HangupConfig | None = None
    record: bool = True
    max_duration_s: int
    llm_timeout_s: float | None = None
    silence_timeout_s: int | None = None
    idle: IdleConfig | None = None
    voicemail: VoicemailConfig | None = None
    stt_fallbacks: list[AgentModel] = Field(default_factory=list[AgentModel])
    tts_fallbacks: list[AgentModel] = Field(default_factory=list[AgentModel])
    tools: list[AgentTool] = Field(default_factory=list[AgentTool])
    state_fields: dict[str, Visibility] = Field(default_factory=dict[str, Visibility])
    view: str | None = None
    events: dict[str, list[EventSource]] = Field(default_factory=dict[str, list[EventSource]])
    judges: JudgesDeclared | None = None
    personas: PersonasDeclared | None = None
    hold: HoldConfig | None = None
    widget: WidgetLook | None = None
    monitors: list[MonitorDeclared] | None = None
    # The settings the class itself declares, by the names it declares them under.
    fixed: list[str] = Field(default_factory=list[str])


# ── the stages on their keys: GET /v1/agents/{slug}/provider-keys ──


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
    commits_when_told: bool = False
    turn_model: Literal["v1-mini", "smart-turn-v3"] = "smart-turn-v3"
    request: dict[str, Any] = Field(default_factory=dict[str, Any])
    lent: bool = False
    fallbacks: list["RunningStage"] = Field(default_factory=list["RunningStage"])


class TelemetryTarget(WireModel):
    """The org's own collector, headers opened, for the worker to export the call's spans to."""

    endpoint: str
    headers: dict[str, str] = Field(default_factory=dict[str, str])
    pii: bool = False


# A worker of the release before 2026-11 refuses a field it does not know here: nothing is added to
# this answer, or to a stage of it, until that release is gone.
class PipelineKeys(WireModel):
    """GET /v1/agents/{slug}/provider-keys: the stages on their keys, and where traces go."""

    llm: RunningStage
    stt: RunningStage
    tts: RunningStage
    # A voice call's whole conversation, where the agent names a model that hears and speaks itself.
    realtime: RunningStage | None = None
    telemetry: TelemetryTarget | None = None


# ── the hold melody: GET /v1/agents/{slug}/hold-audio ──

# Seconds of the agent's quiet before the melody starts, when the org set none: a tool or a model
# that answers inside it plays nothing.
HOLD_AFTER_S = 2.5


# Read by a worker of either release, which refuses a field it does not know: nothing is added until the
# release before 2026-11 is gone.
class HoldAudio(WireModel):
    """What a caller hears while a tool runs, and after how long: the runtime's melody, silence, or the org's clip."""

    played: HoldPlayed
    sha256: str | None = None
    # The hash of the clip as it was uploaded, before conversion: what a class that ships it says.
    source_sha256: str | None = None
    seconds: float | None = None
    name: str | None = None
    # The wait that plays: the class's, else the org's, else the runtime's.
    after_s: float = HOLD_AFTER_S
    # True when the agent's class declares its melody: the endpoints write nothing but the class's own file.
    fixed: bool = False
