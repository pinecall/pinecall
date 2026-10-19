"""A plugin's class for a stage is found where the plugin keeps it: at the top of its module, or an
LLM on the Responses API in its `responses` module (xAI's Grok); its realtime model's class in its
`realtime` module, and the models that class runs where the plugin names them."""

import types
from typing import Literal

from pinecall_runtime.providers.service.plugins import class_path, realtime_models, realtime_path


class LLM:
    """A model class."""


class STT:
    """Ears."""


class Talks:
    """A realtime model's class that types the models it runs, as xAI's does."""

    def __init__(self, *, model: Literal["voice-1", "voice-3"] | str = "voice-1") -> None:
        self.model = model


class TalksAnything:
    """A realtime model's class typed as any string, as OpenAI's is; the plugin lists its models apart."""

    def __init__(self, *, model: str = "rt") -> None:
        self.model = model


def test_a_class_at_the_top_of_the_module_is_found_there() -> None:
    module = types.SimpleNamespace(LLM=LLM, STT=STT)
    assert class_path(module, "llm") == "LLM"
    assert class_path(module, "stt") == "STT"
    assert class_path(module, "tts") is None


def test_an_llm_kept_in_the_responses_module_is_found_there() -> None:
    module = types.SimpleNamespace(STT=STT, responses=types.SimpleNamespace(LLM=LLM))
    assert class_path(module, "llm") == "responses.LLM"


def test_the_top_of_the_module_comes_first() -> None:
    module = types.SimpleNamespace(LLM=LLM, responses=types.SimpleNamespace(LLM=STT))
    assert class_path(module, "llm") == "LLM"


def test_a_realtime_class_in_the_realtime_module_lists_the_models_its_model_argument_types() -> None:
    module = types.SimpleNamespace(LLM=LLM, realtime=types.SimpleNamespace(RealtimeModel=Talks))
    assert realtime_path(module) == "realtime.RealtimeModel"
    assert realtime_models(module) == ("voice-1", "voice-3")


def test_a_realtime_class_typed_as_any_string_lists_the_models_its_plugin_names() -> None:
    listed = types.SimpleNamespace(RealtimeModels=Literal["rt", "rt-2"])
    module = types.SimpleNamespace(RealtimeModel=TalksAnything, models=listed)
    assert realtime_path(module) == "RealtimeModel"
    assert realtime_models(module) == ("rt", "rt-2")


def test_a_plugin_with_no_realtime_class_lists_no_realtime_model() -> None:
    module = types.SimpleNamespace(LLM=LLM, STT=STT)
    assert realtime_path(module) is None
    assert realtime_models(module) == ()
