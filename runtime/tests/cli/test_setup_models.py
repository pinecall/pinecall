"""What `setup` runs a call on: the row for each mix of local stages and vendors, the keys each needs, the turn."""

import pytest

from pinecall_runtime.cli import setup_models as models
from pinecall_runtime.exceptions import ValidationError


def test_every_stage_local_names_the_three_servers_on_loopback() -> None:
    """Every stage on the openai plugin, each with its server's base_url; Smart Turn ends the turn; nothing priced."""
    row = models.row_of(models.ALL_LOCAL)
    assert {stage: (one.vendor, one.model) for stage, one in row.defaults.items()} == {
        "llm": ("openai", models.LOCAL_LLM),
        "stt": ("openai", models.LOCAL_STT),
        "tts": ("openai", models.LOCAL_TTS),
    }
    urls = {key: options.options["base_url"] for key, options in row.tuning.items()}
    assert urls == {
        "llm/openai": "http://127.0.0.1:11434/v1",
        "tts/openai": "http://127.0.0.1:8880/v1",
        "stt/openai": "http://127.0.0.1:8000/v1",
    }
    assert row.tuning["stt/openai"].turn_model == "smart-turn-v3"
    assert row.judge is not None and row.judge.llm.model == models.LOCAL_LLM
    assert row.caller is not None and row.caller.llm is not None and row.caller.llm.model == models.LOCAL_LLM
    assert row.embedding is not None and row.embedding.model == models.LOCAL_EMBEDDER
    assert models.LOCAL_LLM in row.rates and models.LOCAL_STT in row.rates


def test_a_mix_keeps_the_local_stages_servers_and_names_the_vendors_bare() -> None:
    """Anthropic thinks and judges; the local ears keep their base_url and Smart Turn; the local voice its voices."""
    row = models.row_of(models.Choices(stt=models.LOCAL, turn="smart-turn", llm="anthropic", tts=models.LOCAL))
    assert row.defaults["llm"].vendor == "anthropic" and row.defaults["llm"].model is None
    assert "llm/openai" not in row.tuning and "stt/openai" in row.tuning and "tts/openai" in row.tuning
    assert row.judge is not None and row.judge.llm.vendor == "anthropic"
    assert row.caller is not None and row.caller.llm is not None and row.caller.llm.vendor == "anthropic"
    assert row.voices == {"openai/es": "ef_dora", "openai/en": "af_heart"}


def test_every_stage_on_a_vendor_leaves_the_ears_own_endpointing_and_the_embedder_local() -> None:
    """No turn model when the ears end the turn; no voices listed for a vendor; bge-m3 stays for memory and bases."""
    row = models.row_of(models.ALL_KEYS)
    assert {stage: one.vendor for stage, one in row.defaults.items()} == {
        "stt": "deepgram",
        "llm": "anthropic",
        "tts": "cartesia",
    }
    assert row.tuning == {} and row.voices == {}
    assert row.embedding is not None and row.embedding.url == "http://127.0.0.1:11434/v1"
    livekit = models.row_of(models.Choices(stt="deepgram", turn="livekit", llm="anthropic", tts="cartesia"))
    assert livekit.tuning["stt/deepgram"].turn_model == "v1-mini"


def test_the_keys_a_mix_needs_and_where_each_came_from(monkeypatch: pytest.MonkeyPatch) -> None:
    """One variable per vendor of yours, read from the environment; the local servers' word for openai always."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-x")
    monkeypatch.setenv("ACME_API_KEY", "ak-x")
    given, read = models.keys_for(models.Choices(stt=models.LOCAL, llm="anthropic", tts="acme"), asking=False)
    assert given == {"acme": "ak-x", "anthropic": "sk-ant-x", "openai": "local"}
    assert read == ["ACME_API_KEY", "ANTHROPIC_API_KEY"]
    assert models.key_variable("assemblyai") == "ASSEMBLYAI_API_KEY"
    monkeypatch.delenv("ACME_API_KEY")
    with pytest.raises(ValidationError, match="acme needs a key: set ACME_API_KEY"):
        models.keys_for(models.Choices(tts="acme"), asking=False)


def test_the_turn_is_one_of_three_and_the_local_ears_cannot_end_it() -> None:
    """Whisper has no endpointing of its own: `stt` as the turn is refused naming the two that work."""
    with pytest.raises(ValidationError, match="--turn is one of stt, smart-turn, livekit"):
        models.turn_of("vad")
    assert models.turn_of(" Smart-Turn ") == "smart-turn"
    with pytest.raises(ValidationError, match="the local ears \\(Whisper\\) end no turn themselves"):
        models.check_choices(models.Choices(turn="stt"))


def test_a_choice_may_name_the_model_after_its_vendor() -> None:
    """`hf/Qwen/Qwen2.5-3B-Instruct` is the vendor hf running that model; a bare vendor runs its plugin's own."""
    assert (models.vendor_of("hf/Qwen/Qwen2.5-3B-Instruct"), models.model_of("hf/Qwen/Qwen2.5-3B-Instruct")) == (
        "hf",
        "Qwen/Qwen2.5-3B-Instruct",
    )
    assert (models.vendor_of("anthropic"), models.model_of("anthropic")) == ("anthropic", None)
    row = models.row_of(models.Choices(stt="deepgram", turn="stt", llm="anthropic/claude-haiku-5-5", tts="cartesia"))
    assert (row.defaults["llm"].vendor, row.defaults["llm"].model) == ("anthropic", "claude-haiku-5-5")
    assert row.judge is not None and row.judge.llm.model == "claude-haiku-5-5"
