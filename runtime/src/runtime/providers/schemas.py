"""The bodies of the providers endpoints: what an org can run, its keys, voices, transcriptions, advice, telemetry."""

from typing import Any, Literal

from pydantic import Field

from runtime.enums import Stage
from runtime.kit.schemas import Row, Schema

# ── what an org can run ──


# v1's row, which the console reads, and `availability` and `broken` beside it: `standing` is
# `availability` in v1's words, and the fields v1 read off a table in code are empty here.
class ProviderRow(Row):
    """One installed vendor: what it does, whose key runs it for this org, and why not."""

    name: str
    does: list[Stage]
    aliases: list[str] = Field(default_factory=list[str])
    note: str
    standing: Literal["ready", "no plugin", "no key", "its own"]
    ready: bool
    env: str | None = None
    extra: str
    voices_listed: bool
    availability: Literal["yours", "offered", "bring your own", "broken"]
    broken: str | None


class ModelPrice(Row):
    """What a model costs in US dollars, as the row's rates say: per million tokens, per character, second or minute."""

    input: float | None = None
    output: float | None = None
    characters: float | None = None
    audio_seconds: float | None = None
    minutes: float | None = None


class ModelChoice(Row):
    """One model a picker offers of a vendor for a stage: its name, whether this org may run it, its price."""

    model: str
    name: str
    recommended: bool = False
    # On the org's own key, or lent by the platform; false where only a key of the org's own would run it.
    available: bool
    price: ModelPrice | None = None


class ProvidersResponse(Row):
    """GET /v1/providers: every vendor installed, the defaults per stage, the models named."""

    providers: list[ProviderRow]
    defaults: dict[Stage, str]
    # The picker reads GET /v1/voices; no names are curated in code.
    voices: list[str] = Field(default_factory=list[str])
    models: dict[str, list[str]]
    # `stt/deepgram`: every model the row offers of a vendor for a stage, the recommended first, each saying
    # whether this org may run it; `models` is the ones it may, alone.
    choices: dict[str, list[ModelChoice]] = Field(default_factory=dict[str, list[ModelChoice]])
    # `stt/deepgram`: the model a call runs when none is picked (the row's, else the plugin's own where
    # it says one) and the first of `models`; a vendor absent here decides inside its plugin.
    runs: dict[str, str]
    # `xai`: the models that hear and speak themselves, as the vendor's plugin lists them; the agent's
    # `realtime` names one, and its voice calls run on it with no ears and no voice of their own.
    realtime: dict[str, list[str]]


class PluginOption(Row):
    """One keyword argument a vendor's plugin takes for a stage, as a form draws it."""

    name: str
    # The options object it sits in, where the plugin takes one (`params`, `voice_settings`); else null.
    inside: str | None = None
    kind: Literal["text", "number", "integer", "boolean", "choice", "list", "json"]
    # A closed list the plugin names; with `open`, any other text is taken too.
    choices: list[str] = Field(default_factory=list[str])
    open: bool = False
    default: Any = None
    required: bool = False


class PluginOptions(Row):
    """GET /v1/providers/{vendor}/options: what the vendor's plugin takes for a stage, the settings' knobs left out."""

    vendor: str
    modality: Stage
    builds: str
    options: list[PluginOption]


class AdvisedStage(Row):
    """One stage of GET /v1/providers/advice: the choice an agent names, whose key it runs on, what is served."""

    stage: Stage
    choice: str
    runs_on: str
    served: list[str]


class Advice(Row):
    """GET /v1/providers/advice: what this host advises the org to run, and, for its operator, the machine."""

    stages: list[AdvisedStage]
    # What the host lends: None lends every vendor whose key it holds, empty lends nothing.
    lends: list[str] | None
    judge: str | None
    caller: str | None
    # The machine the gateway runs on, as `setup --recommend` reads it: for the box's operator, and
    # only where the row's open-model servers are on this same host.
    machine: dict[str, Any] | None


# ── vendor keys ──


class VendorsResponse(Row):
    """GET /v1/provider-keys: the vendors the org brought its own credentials for, never one."""

    vendors: list[str]


# One key, or the whole object a plugin's constructor takes (`speech_key` and `speech_region`).
class ProviderKeyRequest(Schema):
    """PUT /v1/provider-keys/{vendor}: the org's own credentials for one vendor."""

    key: str | None = None
    credentials: dict[str, Any] | None = None


# ── voices ──


class ListedVoice(Row):
    """One voice as the picker shows it: the id the `voice` setting takes, and what to choose by."""

    id: str
    name: str
    language: str
    description: str
    gender: str
    country: str
    accent: str


class VoicesListed(Row):
    """GET /v1/voices?tts=&language=: a vendor's own voices, in the vendor's order."""

    tts: str
    language: str | None
    voices: list[ListedVoice]


class VoiceSampleRequest(Schema):
    """POST /v1/voices/sample: which vendor, voice, model and words to hear; the answer is WAV."""

    tts: str
    voice: str
    model: str | None = None
    language: str | None = None
    text: str | None = None


# ── transcriptions ──


class TranscriptionResponse(Row):
    """POST /v1/transcriptions: the note's words, the language most of them were in, the audio heard."""

    text: str
    language: str | None
    audio_ms: int
    vendor: str


class DictationTokenResponse(Row):
    """POST /v1/transcriptions/token: what a page opens one dictation with, for a minute."""

    token: str
    path: str
    expires_in: int
    vendor: str


# ── telemetry ──


class TelemetryRequest(Schema):
    """PUT /v1/telemetry: the collector, its headers (a credential, never read back), and PII."""

    endpoint: str
    headers: dict[str, str] = Field(default_factory=dict[str, str])
    pii: bool = False


class TelemetryResponse(Row):
    """GET /v1/telemetry: the collector and which headers are set; null when traces go nowhere."""

    endpoint: str
    header_names: list[str]
    pii: bool
