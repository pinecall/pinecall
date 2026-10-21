"""The providers row as the operator writes it, and the bodies of the providers endpoints."""

from typing import Any, Literal

from pydantic import ConfigDict, Field

from pinecall_runtime.agents.declaration import Modality
from pinecall_runtime.kit.schemas import Schema
from pinecall_runtime.wire.base import WireModel

type Availability = Literal["yours", "offered", "bring your own", "broken"]
type Standing = Literal["ready", "no plugin", "no key", "its own"]
# The two local end-of-turn models, both read off the audio on the worker's CPU: livekit's own
# (its detector's small version) and Daily's Smart Turn v3 (smart-turn-livekit).
type TurnModel = Literal["v1-mini", "smart-turn-v3"]

# The width of every halfvec column that holds a vector.
VECTOR_WIDTH = 1024


# ── the providers row, one JSON value in box_settings ──


class Stage(Schema):
    """A vendor and, when not the plugin's own, its model; a default names who takes over."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    vendor: str
    model: str | None = None
    # A default stage's vendors in the order they take over when the one before fails.
    fallbacks: tuple["Stage", ...] = ()


class Rate(Schema):
    """What a model costs in US dollars: per million tokens, per character, second or minute."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    input: float | None = None
    output: float | None = None
    # Omitted, a cache read costs what fresh input does.
    cached_input: float | None = None
    cache_creation: float | None = None
    characters: float | None = None
    audio_seconds: float | None = None
    # A phone leg's minute, each one begun billed whole.
    minutes: float | None = None
    as_of: str = ""


class StageOptions(Schema):
    """What one vendor is told for one stage: which class it builds and the kwargs it is given."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    # The plugin's class where it is not the one named LLM, STT or TTS (`STTv2`).
    builds: str | None = None
    options: dict[str, Any] = Field(default_factory=dict[str, Any])
    # The ears end the turn themselves, so the session stacks no detector on top.
    ends_the_turn: bool = False
    # Where they do not, which local model reads the end of the turn off the audio; None is the
    # platform's, Smart Turn v3.
    turn_model: TurnModel | None = None
    # What every request of an llm stage carries beside the conversation, in the vendor's own
    # field names (`{"thinking": {"type": "disabled"}}`): livekit's extra_kwargs, each request.
    request: dict[str, Any] = Field(default_factory=dict[str, Any])


class KeptVoice(Schema):
    """A voice the row lists for a vendor, as a picker shows it: its id and what to choose by."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    name: str
    gender: str = ""
    # Where the accent is from: `ES`, `MX`; a language code does not tell them apart.
    country: str = ""
    accent: str = ""
    description: str = ""


class Judge(Schema):
    """The model that judges a finished call, on the box's key, and what one call may spend."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    llm: Stage
    ceiling_usd: float


class Caller(Schema):
    """A simulated caller: what one call's may spend, and the model its lines are improvised on."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ceiling_usd: float = Field(gt=0)
    # A persona that names no model is played on this one; absent, on the box's default llm.
    llm: Stage | None = None


class Embedding(Schema):
    """The one embedder this box runs, on its own key; every base and fact is in its space."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    # The box's `credentials/<vendor>` row holds its key.
    vendor: str
    url: str
    model: str
    # Two wire formats: `embeddings` takes texts, `contextual` takes documents of chunks.
    shape: Literal["embeddings", "contextual"]
    dimensions: int = VECTOR_WIDTH


class Catalog(Schema):
    """The operator's choices: defaults, what each vendor is told, what a model costs, the judge."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    # The stage an agent runs where it names no vendor.
    defaults: dict[Modality, Stage]
    # `tts/elevenlabs`: the model a vendor named alone runs, where the plugin's own is not.
    models: dict[str, str] = Field(default_factory=dict[str, str])
    # `stt/cartesia`: the models a picker offers of a vendor for a stage, beside the one `models` names;
    # `providers models <file> --apply` writes them from the models file, `setup` the ones the package ships.
    offered: dict[str, tuple[str, ...]] = Field(default_factory=dict[str, tuple[str, ...]])
    # `cartesia/es`: the voice an agent that names none speaks with.
    voices: dict[str, str] = Field(default_factory=dict[str, str])
    # `cartesia/es`: the voices a picker offers, where the vendor's plugin lists none of its own.
    listed: dict[str, tuple[KeptVoice, ...]] = Field(default_factory=dict[str, tuple[KeptVoice, ...]])
    # `stt/deepgram`: what that vendor is told for that stage; `llm/anthropic/claude-haiku-5-5`
    # for the models whose id starts so, the longest such key replacing the vendor's whole.
    tuning: dict[str, StageOptions] = Field(default_factory=dict[str, StageOptions])
    # Languages the ears listen for beside the call's own.
    hints: tuple[str, ...] = ()
    # A model's price, by the longest prefix of its id: dated snapshots price by family.
    rates: dict[str, Rate] = Field(default_factory=dict[str, Rate])
    judge: Judge | None = None
    # Absent: a simulated caller spends what its turns ask, as before the row named one.
    caller: Caller | None = None
    # `es`: the line a voice reads in the picker.
    lines: dict[str, str] = Field(default_factory=dict[str, str])
    embedding: Embedding | None = None

    @property
    def default_vendors(self) -> dict[Modality, str]:
        """The vendor each stage runs by default."""
        return {modality: stage.vendor for modality, stage in self.defaults.items()}


# ── the bodies of the endpoints ──


# v1's row, which the console reads, and `availability` and `broken` beside it: `standing` is
# `availability` in v1's words, and the fields v1 read off a table in code are empty here.
class ProviderRow(WireModel):
    """One installed vendor: what it does, whose key runs it for this org, and why not."""

    name: str
    does: list[Modality]
    aliases: list[str]
    note: str
    standing: Standing
    ready: bool
    env: str | None
    extra: str
    voices_listed: bool
    availability: Availability
    broken: str | None


class Catalogue(WireModel):
    """GET /v1/providers: every vendor installed, the defaults per stage, the models named."""

    providers: list[ProviderRow]
    defaults: dict[Modality, str]
    # The picker reads GET /v1/voices; no names are curated in code.
    voices: list[str]
    models: dict[str, list[str]]
    # `xai`: the models that hear and speak themselves, as the vendor's plugin lists them; the agent's
    # `realtime` names one, and its voice calls run on it with no ears and no voice of their own.
    realtime: dict[str, list[str]]


class AdvisedStage(WireModel):
    """One stage of GET /v1/providers/advice: the choice an agent names, whose key it runs on, what is served."""

    stage: Modality
    choice: str
    runs_on: str
    served: list[str]


class Advice(WireModel):
    """GET /v1/providers/advice: what this host advises the org to run, and, for its operator, the machine."""

    stages: list[AdvisedStage]
    # What the host lends: None lends every vendor whose key it holds, empty lends nothing.
    lends: list[str] | None
    judge: str | None
    caller: str | None
    # The machine the gateway runs on, as `setup --recommend` reads it: for the box's operator, and
    # only where the row's open-model servers are on this same host.
    machine: dict[str, Any] | None


class VendorsResponse(WireModel):
    """GET /v1/provider-keys: the vendors the org brought its own credentials for, never one."""

    vendors: list[str]


# One key, or the whole object a plugin's constructor takes (`speech_key` and `speech_region`).
class ProviderKeyRequest(WireModel):
    """PUT /v1/provider-keys/{vendor}: the org's own credentials for one vendor."""

    key: str | None = None
    credentials: dict[str, Any] | None = None


class ListedVoice(WireModel):
    """One voice as the picker shows it: the id the `voice` setting takes, and what to choose by."""

    id: str
    name: str
    language: str
    description: str
    gender: str
    country: str
    accent: str


class VoicesListed(WireModel):
    """GET /v1/voices?tts=&language=: a vendor's own voices, in the vendor's order."""

    tts: str
    language: str | None
    voices: list[ListedVoice]


class TranscriptionResponse(WireModel):
    """POST /v1/transcriptions: the note's words, the language most of them were in, the audio heard."""

    text: str
    language: str | None
    audio_ms: int
    vendor: str


class DictationTokenResponse(WireModel):
    """POST /v1/transcriptions/token: what a page opens one dictation with, for a minute."""

    token: str
    path: str
    expires_in: int
    vendor: str


class VoiceSampleRequest(WireModel):
    """POST /v1/voices/sample: which vendor, voice, model and words to hear; the answer is WAV."""

    tts: str
    voice: str
    model: str | None = None
    language: str | None = None
    text: str | None = None
