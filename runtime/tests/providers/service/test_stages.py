"""A stage is built by its plugin's class: the words the ears expect under the name it takes them, the
language inside a single options object, a voice under its argument or as the model, a number as the
type its parameter wants, and a realtime model by the plugin's realtime class or not at all."""

import dataclasses
from dataclasses import dataclass
from typing import Never, override

import pytest
from livekit.agents import stt, tts

from runtime.enums import Stage
from runtime.exceptions import ValidationError
from runtime.providers.service import plugins, signatures, stages
from runtime.providers.service.llm_requests import LLMWithRequest
from runtime.providers.stage import Running
from tests.fakes import talker
from tests.fakes.acme import ACME, AcmeLLM
from tests.fakes.plugins import install_plugin

HEAR = ("Brisa", "Médano")


@dataclass(frozen=True)
class Patient:
    """A turn that waits this long in silence, and says nothing else."""

    endpointing_ms: int | None = None
    min_interruption_words: int | None = None
    eot_threshold: float | None = None
    eager_eot_threshold: float | None = None
    min_interruption_ms: int | None = None


class _Ears(stt.STT[Never]):
    """Ears that keep what they were built with."""

    def __init__(self, **given: object) -> None:
        super().__init__(capabilities=stt.STTCapabilities(streaming=True, interim_results=True))
        self.given = given

    @override
    async def _recognize_impl(self, *args: object, **kwargs: object) -> stt.SpeechEvent:
        raise NotImplementedError


class TermsAsAnArgument(_Ears):
    """As Deepgram's and Cartesia's: `keyterm=[...]`."""

    def __init__(self, *, api_key: str, language: str | None = None, keyterm: list[str] | None = None) -> None:
        super().__init__(api_key=api_key, language=language, keyterm=keyterm)


@dataclass
class Context:
    terms: list[str] | None = None
    text: str | None = None


@dataclass
class Options:
    model: str = "rt"
    language_hints: list[str] | None = None
    context: Context | str | None = None


class TermsInsideItsOptions(_Ears):
    """As Soniox's: `params=STTOptions(language_hints=[...], context=ContextObject(terms=[...]))`."""

    def __init__(self, *, api_key: str, params: Options | None = None) -> None:
        super().__init__(api_key=api_key, params=params)


class TermsOnSomeModels(_Ears):
    """As Cartesia's: `keyterm` is an argument, and a model that takes none refuses it."""

    def __init__(self, *, api_key: str, model: str = "whisper", keyterm: list[str] | None = None) -> None:
        if keyterm and model == "whisper":
            raise ValueError("keyterm is only supported by turn-detecting models")
        super().__init__(api_key=api_key, model=model, keyterm=keyterm)


class NoTerms(_Ears):
    """Ears that take no words to expect: given none, never refused for it."""

    def __init__(self, *, api_key: str) -> None:
        super().__init__(api_key=api_key)


class HintedEars(_Ears):
    """As Deepgram's `STTv2`: `language_hint=[...]`, which one of its models refuses."""

    def __init__(self, *, api_key: str, language_hint: list[str] | None = None) -> None:
        super().__init__(api_key=api_key, language_hint=language_hint)


# Each kind of ears is a plugin of its own, its STT the class a vendor's would be.
def ears_of(made: type) -> str:
    """The vendor whose plugin's ears are this class."""
    return install_plugin(f"ears-{made.__name__.lower()}", STT=made)


def voice_of(made: type) -> str:
    """The vendor whose plugin's voice is this class."""
    return install_plugin(f"voice-{made.__name__.lower()}", TTS=made)


def _built(made: type, running: Running) -> dict[str, object]:
    ears = stages.stt_of(dataclasses.replace(running, vendor=ears_of(made)), None, HEAR)
    assert isinstance(ears, _Ears)
    return ears.given


def test_ears_that_take_an_argument_for_them_get_the_words_there() -> None:
    given = _built(TermsAsAnArgument, Running(vendor="v", credentials="k", language="es"))
    assert given["keyterm"] == list(HEAR)
    assert given["language"] == "es"


def test_ears_that_take_one_options_object_get_the_words_and_the_language_inside_it() -> None:
    given = _built(TermsInsideItsOptions, Running(vendor="v", credentials="k", language="es-UY"))
    assert given["params"] == Options(language_hints=["es"], context=Context(terms=list(HEAR)))


def test_what_the_row_put_in_the_options_object_stands() -> None:
    row = {"params": {"model": "rt-pro", "language_hints": ["pt"]}}
    given = _built(TermsInsideItsOptions, Running(vendor="v", credentials="k", language="es", options=row))
    assert given["params"] == Options(model="rt-pro", language_hints=["pt"], context=Context(terms=list(HEAR)))


def test_the_model_named_goes_inside_the_options_object_of_ears_that_take_no_model_argument() -> None:
    """Soniox's `params=STTOptions(model=...)`: handed `model=`, it refused it and the call never started."""
    given = _built(TermsInsideItsOptions, Running(vendor="v", credentials="k", model="stt-rt-v5"))
    assert given["params"] == Options(model="stt-rt-v5", context=Context(terms=list(HEAR)))
    assert "model" not in given
    row = {"params": {"language_hints": ["pt"]}}
    named = Running(vendor="v", credentials="k", model="stt-rt-v5", options=row)
    kept = _built(TermsInsideItsOptions, named)
    assert kept["params"] == Options(model="stt-rt-v5", language_hints=["pt"], context=Context(terms=list(HEAR)))


def test_ears_that_take_no_words_are_built_without_them() -> None:
    assert _built(NoTerms, Running(vendor="v", credentials="k")) == {"api_key": "k"}


def test_a_model_that_refuses_the_words_is_built_without_them() -> None:
    given = _built(TermsOnSomeModels, Running(vendor="v", credentials="k"))
    assert given == {"api_key": "k", "model": "whisper", "keyterm": None}


def test_a_model_that_takes_the_words_gets_them() -> None:
    given = _built(TermsOnSomeModels, Running(vendor="v", credentials="k", model="turns"))
    assert given["keyterm"] == list(HEAR)


class _Voice(tts.TTS[Never]):
    """A voice that keeps what it was built with."""

    def __init__(self, **given: object) -> None:
        super().__init__(capabilities=tts.TTSCapabilities(streaming=False), sample_rate=24000, num_channels=1)
        self.given = given

    @override
    def synthesize(self, text: str, *, conn_options: object = None) -> tts.ChunkedStream:
        raise NotImplementedError


class VoiceIsTheModel(_Voice):
    """As Deepgram's: no voice argument, the voice named in the model (`aura-2-celeste-es`)."""

    def __init__(self, *, api_key: str, model: str = "aura-2-thalia-en") -> None:
        super().__init__(api_key=api_key, model=model)


class VoiceAsAnArgument(_Voice):
    """As Gemini's: `voice_name` beside the model."""

    def __init__(self, *, api_key: str, model: str = "tts", voice_name: str = "Kore") -> None:
        super().__init__(api_key=api_key, model=model, voice_name=voice_name)


def _spoken(made: type, running: Running) -> dict[str, object]:
    voice = stages.tts_of(dataclasses.replace(running, vendor=voice_of(made)))
    assert isinstance(voice, _Voice)
    return voice.given


def test_a_voice_whose_plugin_takes_no_voice_argument_is_the_model_it_speaks_with() -> None:
    running = Running(vendor="v", credentials="k", model="aura-2", voice="aura-2-celeste-es")
    assert _spoken(VoiceIsTheModel, running) == {"api_key": "k", "model": "aura-2-celeste-es"}
    plain = Running(vendor="v", credentials="k", model="aura-2-thalia-en")
    assert _spoken(VoiceIsTheModel, plain) == {"api_key": "k", "model": "aura-2-thalia-en"}


def test_a_voice_whose_plugin_takes_one_goes_there_and_the_model_stays() -> None:
    running = Running(vendor="v", credentials="k", model="flash-lite-tts", voice="Puck")
    given = _spoken(VoiceAsAnArgument, running)
    assert (given["model"], given["voice_name"]) == ("flash-lite-tts", "Puck")


def test_a_voice_is_not_refused_by_a_tts_with_no_voice_argument() -> None:
    signatures.refuse_untaken(Stage.tts, Running(vendor=voice_of(VoiceIsTheModel), credentials="k"), ["voice"])


def test_the_platforms_hints_reach_the_ears_unless_the_row_names_them() -> None:
    """Deepgram's `flux-general-en` refuses any `language_hint` at the socket: the row for it names none."""
    hinted = _built(HintedEars, Running(vendor="v", credentials="k", hints=("es", "en")))
    assert hinted["language_hint"] == ["es", "en"]
    row: dict[str, list[str]] = {"language_hint": []}
    told = _built(HintedEars, Running(vendor="v", credentials="k", hints=("es", "en"), options=row))
    assert told["language_hint"] == []


# 2026-11-06: on Scribe `endpointing_ms` was refused as untaken, and the agent spoke over callers who paused.
def test_the_silence_is_the_detectors_on_ears_that_leave_the_turn_open_and_the_ears_own_where_they_end_it() -> None:
    patient = Patient(endpointing_ms=800)
    vendor = ears_of(NoTerms)
    voice = Running(vendor=vendor, credentials="k")
    signatures.refuse_untaken_settings(Running(vendor=vendor, credentials="k"), voice, patient, sets_a_voice=False)
    with pytest.raises(ValidationError, match="takes no endpointing_ms"):
        ears = Running(vendor=vendor, credentials="k", ends_the_turn=True)
        signatures.refuse_untaken_settings(ears, voice, patient, sets_a_voice=False)


def test_an_option_written_as_a_whole_number_reaches_a_float_parameter_as_a_float() -> None:
    """R F15: `--tts-option speed=1.0` reached cartesia as 1 (JSON has one number), refused as no float."""
    built = stages.llm_of(Running(ACME, "k", options={"temperature": 1}))
    assert isinstance(built, LLMWithRequest) and isinstance(built.built, AcmeLLM)
    temperature = built.built.given["temperature"]
    assert (temperature, type(temperature)) == (1.0, float)


# ── a realtime model ──


@pytest.fixture
def vendor() -> str:
    """The talker vendor, installed as a plugin."""
    return talker.install()


def test_the_realtime_class_is_built_with_the_key_the_model_and_the_options(vendor: str) -> None:
    running = Running(vendor=vendor, credentials="k", model="voice-3", builds="LLM", options={"voice": "eve"})
    built = stages.build_realtime(running)
    assert isinstance(built, talker.TalkerRealtime)
    assert built.given == {"api_key": "k", "model": "voice-3", "voice": "eve"}


def test_a_vendor_alone_builds_its_plugins_own_realtime_model(vendor: str) -> None:
    built = stages.build_realtime(Running(vendor=vendor, credentials="k"))
    assert isinstance(built, talker.TalkerRealtime)
    assert built.given["model"] == "voice-1"


def test_a_vendor_with_no_realtime_class_has_no_realtime_model() -> None:
    with pytest.raises(ValidationError, match="acme has no model that hears and speaks itself"):
        stages.build_realtime(Running(vendor=ACME, credentials="k", model="acme-1"))


def test_an_llm_that_names_a_realtime_model_or_its_class_is_refused_naming_the_realtime(vendor: str) -> None:
    with pytest.raises(
        ValidationError, match=r"talker/voice-3 hears and speaks itself.*realtime: 'talker/voice-3' in its class"
    ):
        plugins.refuse_realtime_as_llm(vendor, "voice-3", None)
    with pytest.raises(ValidationError, match="hears and speaks itself"):
        plugins.refuse_realtime_as_llm(vendor, talker.PLAIN, "realtime.RealtimeModel")
    plugins.refuse_realtime_as_llm(vendor, talker.PLAIN, None)
