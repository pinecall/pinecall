"""A plugin's class for a stage is found where the plugin keeps it: at the top of its module, or an
LLM on the Responses API in its `responses` module (xAI's Grok)."""

import types

from pinecall_runtime.providers.service.plugins import class_path


class LLM:
    """A model class."""


class STT:
    """Ears."""


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
