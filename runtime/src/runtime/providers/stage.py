"""A stage of a call as values: the model or voice an agent asks for, and the stage resolved onto its key."""

import dataclasses
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, Never

from livekit.agents import llm, stt, tts
from livekit.agents.language import LanguageCode

from runtime.wire.parts import EndOfTurn

# A key alone, or the object a plugin's constructor takes (`speech_key` and `speech_region`).
type Credentials = str | Mapping[str, Any]
# A call's stage as it is built: the plugin's object, or livekit's adapter over several.
type Thinking = llm.LLM[Never] | llm.FallbackAdapter
type Ears = stt.STT[Never] | stt.FallbackAdapter
type Speaking = tts.TTS[Never] | tts.FallbackAdapter

# The two local end-of-turn models, both read off the audio on the worker's CPU: livekit's own
# (its detector's small version) and Daily's Smart Turn v3 (smart-turn-livekit).
type TurnModel = Literal["v1-mini", "smart-turn-v3"]
# The model each end of turn an agent may ask for reads the audio with; `stt` is the ears' own, and no model.
TURN_MODEL_OF: Mapping[EndOfTurn, TurnModel] = {"smart-turn": "smart-turn-v3", "livekit": "v1-mini"}


# The wire says `provider` and keeps it; in here the word is `vendor`, read once where the wire is.
@dataclass(frozen=True, slots=True)
class Voice:
    """The voice an agent asks for: its vendor, and the model, the voice and the plugin's options where it names any."""

    vendor: str
    model: str | None = None
    voice_id: str | None = None
    builds: str | None = None
    options: Mapping[str, Any] = field(default_factory=dict[str, Any])


@dataclass(frozen=True, slots=True)
class Model:
    """The LLM or the ears an agent asks for: its vendor, the model ("" for the vendor named alone) and its knobs."""

    vendor: str
    model: str
    temperature: float | None = None
    builds: str | None = None
    options: Mapping[str, Any] = field(default_factory=dict[str, Any])
    end_of_turn: EndOfTurn | None = None


@dataclass(frozen=True)
class Running:
    """One stage of a call as it runs: vendor, model, key, and what the plugin is told."""

    vendor: str
    credentials: Credentials
    # None: the plugin's own default.
    model: str | None = None
    # The plugin's class, where the operator names one other than LLM, STT or TTS.
    builds: str | None = None
    # The operator's keyword arguments for this vendor and stage, as the plugin names them.
    options: Mapping[str, Any] = field(default_factory=dict[str, Any])
    voice: str | None = None
    language: str | None = None
    # Languages the ears listen for, the call's first.
    hints: tuple[str, ...] = ()
    # The ears end the turn themselves, so the session stacks no detector on top.
    ends_the_turn: bool = False
    # The ears close no segment on their own: the session's VAD tells them to commit at each end of speech.
    commits_when_told: bool = False
    # Which local model reads the end of the turn off the audio, where the ears do not.
    turn_model: TurnModel = "smart-turn-v3"
    # What every request of an llm stage carries beside the conversation, in the vendor's names.
    request: Mapping[str, Any] = field(default_factory=dict[str, Any])
    # On the box's key rather than the org's own.
    lent: bool = False
    # Who takes over, in order, each on its own key: the stage is livekit's FallbackAdapter.
    fallbacks: tuple["Running", ...] = ()

    # One shape: the wire's stage carries these fields under these names (`wire.worker.RunningStage`,
    # filled from this class by its attributes), and this reads them back. A field is added here and
    # there, and mapped by hand nowhere.
    @classmethod
    def read(cls, said: Mapping[str, Any]) -> "Running":
        """The stage a mapping says under this class's own field names, as the wire carries it."""
        named = {one.name for one in dataclasses.fields(cls)} - {"hints", "fallbacks"}
        return cls(
            **{name: value for name, value in said.items() if name in named},
            hints=tuple(said.get("hints") or ()),
            fallbacks=tuple(cls.read(one) for one in said.get("fallbacks") or ()),
        )

    def over(self, *fallbacks: "Running") -> "Running":
        """The same stage with these vendors taking over behind it, in order."""
        return dataclasses.replace(self, fallbacks=fallbacks)

    # The row's order stands but for the vendors `failing` names (over their error line now), which
    # go last, among themselves in the row's order too.
    def behind(self, failing: frozenset[str]) -> "Running":
        """The same chain, the vendors failing now behind the ones that are not."""
        chain = (dataclasses.replace(self, fallbacks=()), *self.fallbacks)
        first, *rest = sorted(chain, key=lambda item: item.vendor in failing)
        return first.over(*rest)


@dataclass(frozen=True, slots=True)
class Pipeline:
    """The three stages of a voice call, each on the key it runs on."""

    llm: Running
    stt: Running
    tts: Running
    # The model a voice call runs on alone, hearing and speaking itself, where the agent names one.
    realtime: Running | None = None

    @classmethod
    def read(cls, said: Mapping[str, Any]) -> "Pipeline":
        """The stages a mapping says, each under its name, as the wire carries them."""
        alone = said.get("realtime")
        return cls(
            llm=Running.read(said["llm"]),
            stt=Running.read(said["stt"]),
            tts=Running.read(said["tts"]),
            realtime=None if alone is None else Running.read(alone),
        )

    # The gateway keeps these with the call's facts: their usage is the operator's to bill.
    @property
    def lent(self) -> list[str]:
        """The vendors the call may run on the box's key, in stage order, once each."""
        each = (item for stage in (self.llm, self.stt, self.tts) for item in (stage, *stage.fallbacks))
        return list(dict.fromkeys(item.vendor for item in each if item.lent))

    def demoting(self, failing: frozenset[str]) -> "Pipeline":
        """The same stages, each with the vendors failing now behind the ones that are not."""
        return Pipeline(
            llm=self.llm.behind(failing),
            stt=self.stt.behind(failing),
            tts=self.tts.behind(failing),
            realtime=self.realtime,
        )


# What a plugin or a row hands back is typed as nothing; this says what it is, once.
def primary_language(language: str | None) -> str | None:
    """The base code of a language (`es` for `es-ES` or `spanish`); vendors refuse full tags."""
    if language is None or not language.strip():
        return None
    return LanguageCode(language.strip()).language
