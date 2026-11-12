"""What a worker and the gateway tell each other over HTTP: its heartbeat, a call's agent, stages, route, legs, log."""

from datetime import date
from typing import Any, Literal

from pydantic import AliasChoices, ConfigDict, Field

from runtime.enums import Channel, Direction, Env, HoldPlayed
from runtime.wire.base import BatchedEntry, Entry, WireModel
from runtime.wire.declaration import (
    DocsConfig,
    GreetingConfig,
    HangupConfig,
    HoldConfig,
    IdleConfig,
    JudgesDeclared,
    MemoryConfig,
    ModelConfig,
    MonitorDeclared,
    PersonasDeclared,
    TurnConfig,
    VoicemailConfig,
    WidgetLook,
)
from runtime.wire.metrics import ModelUsage
from runtime.wire.parts import EndOfTurn, EventSource, PlatformTool, PromptRegion, SideEffect, Visibility

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


# ── a call's route, its legs and whose ring it is: what a worker asks of telephony ──

type Transport = Literal["auto", "udp", "tcp", "tls"]


# The worker's scope rides the query of every endpoint it asks (`?org=&env=&holder=`), read by its key's
# resolution; a query model that refused the three answered 422 to every dial (2026-11-05).
class WorkerQuery(WireModel):
    """What every question of a worker carries: the scope its dispatch named, read where its key is resolved."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)

    org: str | None = None
    env: Env | None = None
    holder: str | None = None


class RouteQuery(WorkerQuery):
    """GET /v1/routes: the number a call rang, or nothing for the routes of the scope its dispatch named."""

    number: str | None = None
    channel: Channel = Channel.phone


# Read by a worker of either release, which refuses a field it does not know: nothing is added until
# the release before 2026-11 is gone.
class RouteRow(WireModel):
    """One route as a worker and the operator read it: which org's agent answers a number, on a channel, in an env."""

    org: str
    number: str
    agent: str
    channel: Channel
    env: Env
    managed: bool


class LegTrunkQuery(WorkerQuery):
    """A worker asking how to dial a leg of a call: to whom, from which of the org's numbers."""

    to: str
    call: str
    shown: str | None = Field(None, alias="from")


class ColdTransferQuery(WorkerQuery):
    """A worker asking whether the caller may be sent on: to whom, from which call."""

    to: str
    call: str


class LegTrunk(WireModel):
    """How the worker dials a leg: the host, its transport, the pair, the number shown."""

    hostname: str
    transport: Transport
    username: str
    password: str
    shown: str


class LegTrunkResponse(WireModel):
    """GET /v1/agents/{slug}/outbound-trunk: the leg's trunk, inline, after the guards."""

    trunk: LegTrunk


class RingHandoff(WireModel):
    """Where a production ring goes: a developer's scope and its fleet, or nowhere (null)."""

    holder: str | None = None
    fleet: str | None = None
    # Where the sandbox has a LiveKit of its own: the ring is dialled to its SIP through this.
    trunk: LegTrunk | None = None


# The org alone: the phone is a member's, but they named no agent and the org holds several. The org
# and the agent, no holder: nobody holds that agent in the sandbox right now.
class RingAtTestLine(WireModel):
    """GET /v1/test-line/rings-for: whose sandbox agent a ring at the test line is for; nulls for nobody's."""

    org: str | None = None
    agent: str | None = None
    holder: str | None = None


# ── a call's log: what its worker opens it with, writes to it, asks of it and ends it with ──

# The bodies of the worker's endpoints on its call (`POST /v1/calls` and what follows), as the release
# before 2026-11 wrote them in `calls/schemas`: its workers, draining calls for up to an hour, send
# these to the new gateways, and after a rollback these workers send them to its gateways. A field
# is added with a default, never renamed, retyped or removed, until that release is gone.


class _OfACall(WireModel):
    # What a call is was a dataclass of that release, which read past a key it did not know.
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class CallRoute(_OfACall):
    """Which agent answers on a channel and number, and which org owns it, as a worker says it of its call."""

    org: str
    agent: str
    channel: Channel
    number: str | None = None
    label: str | None = None
    env: Env = Env.production
    managed: bool = False


class CallContact(_OfACall):
    """What a worker knows about the caller; a web visitor may be anonymous."""

    id: str | None = None
    phone: str | None = None
    name: str | None = None
    email: str | None = None
    external_id: str | None = None


# Field for field `calls.context.CallContext`, which reads it back (`read_context`) and holds it to its rules.
class CallOpened(_OfACall):
    """A call as its worker sees it when it starts: its id, who calls, the route it came in by, its day."""

    call: str
    channel: Channel
    direction: Direction
    caller: str
    route: CallRoute
    today: date
    pinned_day: date | None = None
    contact: CallContact | None = None
    metadata: dict[str, Any] = Field(default_factory=dict[str, Any])
    run: str | None = None
    persona: str | None = None
    expects: tuple[str, ...] = ()
    holder: str | None = None
    state: dict[str, Any] = Field(default_factory=dict[str, Any])
    continues: str | None = None


class OpenCallRequest(WireModel):
    """What a worker opens a call with, and says again to a gateway that forgot it."""

    agent: str
    context: CallOpened
    # The app socket that must serve it (a spoken golden run); else the one the call reaches.
    app: str | None = None
    # The Twilio account an inbound leg says it came from (X-Twilio-AccountSid); None from any
    # other carrier, or from a worker of an older release.
    carrier_account: str | None = None
    # The test room's own voice and models the worker runs this call on (its dispatch's test values), so
    # the gateway opens the call as it runs: the platform's first words in that language. On the wire
    # it is `tuning`, the word the release before 2026-11 sends.
    test_values: dict[str, Any] | None = Field(default=None, alias="tuning")


class OpenCallResponse(WireModel):
    """What the org's minutes leave the call (null for no limit), and what it says first."""

    seconds_left: int | None
    minutes: int | None
    # An outbound call's AI disclosure, and the notice a recorded call says; null for none.
    disclosure: str | None = None
    recording_notice: str | None = None
    # The turns of the call this one continues, oldest first; empty for a call of its own.
    history: list[Entry] = Field(default_factory=list[Entry])


class AppendEntryRequest(WireModel):
    """One entry a worker writes to its call's log."""

    type: str
    data: dict[str, Any]
    ephemeral: bool | None = None


# `after` makes a retry safe: the log answers a batch it already took with the seqs it gave it.
class AppendEntriesRequest(WireModel):
    """A worker's entries of its call, in order, after how many the log already took from it."""

    after: int = Field(ge=0)
    entries: list[BatchedEntry]


class AppendEntriesResponse(WireModel):
    """A worker's batch as the log numbered it, in the order it was sent."""

    entries: list[Entry]


# On the entries socket, where a refusal is a frame and not a status: the socket stays open.
class AppendEntriesRefused(WireModel):
    """A batch the gateway refused, with the sentence and the status a request would get."""

    refused: str
    status: int


# `input` is whole and unread by the wire: what recall and search take is the runtime's shape.
class LookupRequest(WireModel):
    """Which platform tool to run for a call's turn, what to run it with, and the turn it joins."""

    tool: PlatformTool
    input: dict[str, Any]
    speech_id: str | None = None


class LookupResponse(WireModel):
    """What the tool found, as the model reads it, and how long finding it took."""

    output: dict[str, Any]
    took_ms: float


class RememberResponse(WireModel):
    """How many memory operations a call produced, and how long remembering took."""

    ops: int
    took_ms: float


class RecordingKeyResponse(WireModel):
    """The key a call's recording is sealed under before it is stored: 32 bytes, base64url."""

    key: str


# Read by a worker of either release: the release before 2026-11 declared it among its agents' bodies,
# with these three fields.
class JudgingSettings(WireModel):
    """GET /v1/calls/{call}/judging: whether the call's org judges at hang-up, and the ceiling a judge may spend."""

    on: bool
    ceiling_usd: float | None
    # The model the org's calls are judged on; null: the platform's. This answer has always left it null.
    model: ModelConfig | None = None


class SealCallRequest(WireModel):
    """The end of a call as its worker hands it to the gateway, which prices, judges and seals."""

    usage: list[ModelUsage]
    outcome: str
    recording: str | None = None
    # The vendors that ran on the box's own key: the operator bills their usage.
    lent: list[str] = Field(default_factory=list[str])
