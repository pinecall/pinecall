"""What `setup` runs a call on: the row for the local models, the row for the vendors keyed, the one question."""

import pytest

from pinecall_runtime.cli import setup_models as models


def test_the_local_row_names_the_three_servers_on_loopback() -> None:
    """Every stage on the openai plugin, each with its own server's base_url, the models named, nothing priced."""
    row = models.local_row("gemma4:4b", "Systran/faster-whisper-small", chat_only=False)
    assert {stage: (one.vendor, one.model) for stage, one in row.defaults.items()} == {
        "llm": ("openai", "gemma4:4b"),
        "stt": ("openai", "Systran/faster-whisper-small"),
        "tts": ("openai", "kokoro"),
    }
    urls = {key: options.options["base_url"] for key, options in row.tuning.items()}
    assert urls == {
        "llm/openai": "http://127.0.0.1:11434/v1",
        "tts/openai": "http://127.0.0.1:8880/v1",
        "stt/openai": "http://127.0.0.1:8000/v1",
    }
    assert row.judge is not None and row.judge.llm.model == "gemma4:4b"
    assert row.caller is not None and row.caller.llm is not None and row.caller.llm.model == "gemma4:4b"
    assert row.embedding is not None and row.embedding.model == "bge-m3"
    assert "gemma4:4b" in row.rates and "Systran/faster-whisper-small" in row.rates


def test_chat_alone_keeps_no_ears_and_no_voice() -> None:
    """`--chat-only`: the model and the embedder, nothing the worker would need."""
    row = models.local_row("gemma4:4b", "Systran/faster-whisper-small", chat_only=True)
    assert set(row.defaults) == {"llm"}
    assert set(row.tuning) == {"llm/openai"}
    assert row.voices == {}


def test_the_keys_row_runs_on_the_vendors_keyed() -> None:
    """Anthropic thinks when its key is there, else OpenAI; a stage with no key is missing and said."""
    both = models.keys_row(frozenset({"anthropic", "openai", "deepgram", "cartesia"}))
    assert {stage: one.vendor for stage, one in both.defaults.items()} == {
        "llm": "anthropic",
        "stt": "deepgram",
        "tts": "cartesia",
    }
    assert models.missing_stages(both) == ""
    openai_alone = models.keys_row(frozenset({"openai"}))
    assert {stage: one.vendor for stage, one in openai_alone.defaults.items()} == {"llm": "openai"}
    assert models.missing_stages(openai_alone) == "no ears; no voice"
    assert (
        models.missing_stages(models.keys_row(frozenset({"deepgram"})))
        == "no model to think with: chat needs one; no voice"
    )


def test_models_is_one_of_three_words() -> None:
    """The question's answer, as typed."""
    assert models.Models("local") is models.Models.local
    with pytest.raises(ValueError, match="not a valid"):
        models.Models("cloud")
