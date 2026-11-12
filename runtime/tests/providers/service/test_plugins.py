"""A plugin's class for a stage is found where the plugin keeps it: at the top of its module, or an
LLM on the Responses API in its `responses` module (xAI's Grok); its realtime model's class in its
`realtime` module, and the models that class runs where the plugin names them."""

from typing import Literal

from runtime.enums import Stage
from runtime.providers.service.plugins import (
    class_path,
    default_models,
    models_listed,
    realtime_models,
    realtime_path,
)
from tests.fakes.plugins import a_module


class LLM:
    """A model class."""


class STT:
    """Ears, building one model when none is named."""

    def __init__(self, *, model: str = "ears-3") -> None:
        self.model = model


class TTS:
    """A voice that decides its model inside."""

    def __init__(self, *, model: str | None = None) -> None:
        self.model = model


class Talks:
    """A realtime model's class that types the models it runs, as xAI's does."""

    def __init__(self, *, model: Literal["voice-1", "voice-3"] | str = "voice-1") -> None:
        self.model = model


class TalksAnything:
    """A realtime model's class typed as any string, as OpenAI's is; the plugin lists its models apart."""

    def __init__(self, *, model: str = "rt") -> None:
        self.model = model


class Flux:
    """A second class of ears that types the models it runs, as Deepgram's `STTv2` does."""

    def __init__(self, *, model: Literal["flux-en", "flux-multi"] | str = "flux-en") -> None:
        self.model = model


def test_the_models_a_class_lists_are_what_it_types_its_model_argument_with() -> None:
    module = a_module(STT=STT, STTv2=Flux, TTS=TTS)
    assert models_listed(module, "STTv2") == ("flux-en", "flux-multi")
    assert models_listed(module, "STT") == ()
    assert models_listed(module, "TTS") == ()
    assert models_listed(module, "nothing.here") == ()


def test_a_class_at_the_top_of_the_module_is_found_there() -> None:
    module = a_module(LLM=LLM, STT=STT)
    assert class_path(module, Stage.llm) == "LLM"
    assert class_path(module, Stage.stt) == "STT"
    assert class_path(module, Stage.tts) is None


def test_an_llm_kept_in_the_responses_module_is_found_there() -> None:
    module = a_module(STT=STT, responses=a_module(LLM=LLM))
    assert class_path(module, Stage.llm) == "responses.LLM"


def test_the_top_of_the_module_comes_first() -> None:
    module = a_module(LLM=LLM, responses=a_module(LLM=STT))
    assert class_path(module, Stage.llm) == "LLM"


def test_a_stages_default_model_is_what_its_class_builds_when_none_is_named_and_none_where_it_decides_inside() -> None:
    module = a_module(LLM=LLM, STT=STT, TTS=TTS)
    assert default_models(module, {Stage.llm, Stage.stt, Stage.tts}) == {Stage.stt: "ears-3"}


def test_a_realtime_class_in_the_realtime_module_lists_the_models_its_model_argument_types() -> None:
    module = a_module(LLM=LLM, realtime=a_module(RealtimeModel=Talks))
    assert realtime_path(module) == "realtime.RealtimeModel"
    assert realtime_models(module) == ("voice-1", "voice-3")


def test_a_realtime_class_typed_as_any_string_lists_the_models_its_plugin_names() -> None:
    listed = a_module(RealtimeModels=Literal["rt", "rt-2"])
    module = a_module(RealtimeModel=TalksAnything, models=listed)
    assert realtime_path(module) == "RealtimeModel"
    assert realtime_models(module) == ("rt", "rt-2")


def test_a_plugin_with_no_realtime_class_lists_no_realtime_model() -> None:
    module = a_module(LLM=LLM, STT=STT)
    assert realtime_path(module) is None
    assert realtime_models(module) == ()
