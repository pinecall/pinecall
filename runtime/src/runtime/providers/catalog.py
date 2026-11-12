"""The providers row as a value: the operator's choices as the box keeps them, and how its keys are read."""

from collections.abc import Iterable, Iterator
from typing import Any, Literal

from pydantic import ConfigDict, Field

from runtime.enums import Stage
from runtime.kit.db import VECTOR_WIDTH
from runtime.kit.schemas import Schema
from runtime.providers.stage import TurnModel

# The row keys its maps by words joined with a slash: `stage/vendor`, `stage/vendor/model-prefix`,
# `vendor/language`, `vendor/model`. Model ids carry slashes of their own (`openai/gpt-5` on LiveKit
# Inference): the first ends the vendor. Only this module writes or splits such a key.
_SEPARATOR = "/"


def stage_key(stage: Stage | str, vendor: str) -> str:
    """`stt/deepgram`: how the row names a vendor doing a stage."""
    return f"{stage}{_SEPARATOR}{vendor}"


def model_key(vendor: str, model: str) -> str:
    """`cartesia/sonic-3.6`: how the row names a vendor's model."""
    return f"{vendor}{_SEPARATOR}{model}"


def read_stage_key(key: str) -> tuple[str, str]:
    """The stage and the vendor a `stage/vendor` or `stage/vendor/model` key names, as they are written."""
    stage, _, rest = key.partition(_SEPARATOR)
    return stage, rest.partition(_SEPARATOR)[0]


def longest_prefix(keys: Iterable[str], name: str) -> str | None:
    """The longest of the keys the name starts with, so a dated snapshot reads as its family."""
    listed = [key for key in keys if name.startswith(key)]
    return max(listed, key=len) if listed else None


class StageChoice(Schema):
    """A vendor and, when not the plugin's own, its model; a default names who takes over."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    vendor: str
    model: str | None = None
    # A default stage's vendors in the order they take over when the one before fails.
    fallbacks: tuple["StageChoice", ...] = ()

    @property
    def named(self) -> str:
        """`vendor/model`, or the vendor alone where it names no model."""
        return model_key(self.vendor, self.model) if self.model else self.vendor


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
    # The ears close no segment on their own (Scribe realtime with no `server_vad`): the session's
    # VAD tells them to commit at each end of speech it hears.
    commits_when_told: bool = False
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

    llm: StageChoice
    ceiling_usd: float


class Caller(Schema):
    """A simulated caller: what one call's may spend, and the model its lines are improvised on."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ceiling_usd: float = Field(gt=0)
    # A persona that names no model is played on this one; absent, on the box's default llm.
    llm: StageChoice | None = None


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


# Read from Postgres on every call and cached by nobody, on purpose: a key rotated or a default
# changed runs from the next call, and a cache would need invalidating across gateways.
class Catalog(Schema):
    """The operator's choices: defaults, what each vendor is told, what a model costs, the judge."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    # The stage an agent runs where it names no vendor.
    defaults: dict[Stage, StageChoice]
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
    # `cartesia/sonic-3.6`: the name the vendor gives a model where it is not the id; the models file's.
    names: dict[str, str] = Field(default_factory=dict[str, str])
    # `tts/cartesia`: the models a picker leads with for a vendor and stage, in order; the models file's.
    recommended: dict[str, tuple[str, ...]] = Field(default_factory=dict[str, tuple[str, ...]])
    judge: Judge | None = None
    # Absent: a simulated caller spends what its turns ask, as before the row named one.
    caller: Caller | None = None
    # `es`: the line a voice reads in the picker.
    lines: dict[str, str] = Field(default_factory=dict[str, str])
    embedding: Embedding | None = None

    @property
    def default_vendors(self) -> dict[Stage, str]:
        """The vendor each stage runs by default."""
        return {stage: choice.vendor for stage, choice in self.defaults.items()}

    # Never the plugin's own, which Google retires under new users without notice.
    def model_for(self, stage: Stage, vendor: str) -> str | None:
        """The model a vendor named alone runs: the row's, else the default's where the default is that vendor."""
        default = self.defaults.get(stage)
        named = self.models.get(stage_key(stage, vendor))
        return named or (default.model if default is not None and default.vendor == vendor else None)

    def options_for(self, stage: Stage, vendor: str, model: str | None = None) -> StageOptions | None:
        """What a vendor is told for a stage: the longest key naming the model's id, else the vendor's own."""
        own = stage_key(stage, vendor)
        under = f"{own}{_SEPARATOR}"
        prefixes = (key.removeprefix(under) for key in self.tuning if key.startswith(under))
        named = None if model is None else longest_prefix(prefixes, model)
        return self.tuning.get(own if named is None else f"{under}{named}")

    def leads_for(self, stage: Stage, vendor: str) -> tuple[str, ...]:
        """The models a picker leads with for a vendor and stage, in order."""
        return self.recommended.get(stage_key(stage, vendor), ())

    def voice_for(self, vendor: str, language: str | None) -> str | None:
        """The voice a vendor speaks a language with where an agent names none."""
        return None if language is None else self.voices.get(f"{vendor}{_SEPARATOR}{language}")

    def list_voices_for(self, vendor: str, language: str | None = None) -> list[tuple[str, KeptVoice]]:
        """The voices the row lists for a vendor, each with its language: in that language, or in every one."""
        found: list[tuple[str, KeptVoice]] = []
        for key, voices in self.listed.items():
            named, _, spoken = key.partition(_SEPARATOR)
            if named == vendor and (language is None or spoken == language):
                found += [(spoken, voice) for voice in voices]
        return found

    def name_of(self, vendor: str, model: str) -> str:
        """The name the vendor gives a model, where it is not the id."""
        return self.names.get(model_key(vendor, model), model)

    def rate_for(self, model: str) -> Rate | None:
        """The rate whose key is the longest prefix of the model id, so snapshots price by family."""
        key = longest_prefix(self.rates, model)
        return None if key is None else self.rates[key]

    # A carrier prices a leg by the longest prefix of its number, as its own rate tables do.
    def leg_rate_key_for(self, leg: str, number: str) -> str | None:
        """The key of the rate that prices a phone leg (`twilio-inbound/+598`): the longest its number starts with."""
        return longest_prefix(self.rates, f"{leg}{_SEPARATOR}{number}")

    def per_stage(self) -> Iterator[tuple[str, str, tuple[str, ...]]]:
        """Every `stage/vendor` the row names a model for or offers, sorted: the key, its vendor, what it offers."""
        for named in sorted({*self.models, *self.offered}):
            yield named, named.partition(_SEPARATOR)[2], self.offered.get(named, ())

    def tts_vendors_named(self) -> Iterator[str]:
        """The vendor of every `vendor/language` key the row gives a voice or a list of voices."""
        for key in (*self.voices, *self.listed):
            yield key.partition(_SEPARATOR)[0]
