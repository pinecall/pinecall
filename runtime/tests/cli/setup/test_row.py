"""The row `setup` writes for each mix of local stages and vendors: defaults, tuning, judge, caller, rates."""

import pytest

from runtime.cli.setup import choices as models
from runtime.cli.setup.row import list_prices, list_stage_options, row_of
from runtime.enums import Stage
from runtime.providers.catalog import read_stage_key
from runtime.providers.service import plugins


def test_every_stage_local_names_the_three_servers_on_loopback() -> None:
    """Every stage on the openai plugin, each with its server's base_url; Smart Turn ends the turn; nothing priced."""
    row = row_of(models.ALL_LOCAL)
    assert {stage: (one.vendor, one.model) for stage, one in row.defaults.items()} == {
        "llm": ("openai", models.LOCAL_LLM),
        "stt": ("openai", models.LOCAL_STT),
        "tts": ("openai", models.LOCAL_TTS),
    }
    # The three local servers; what the row says of the vendors' own models stands beside them.
    urls = {key: told.options["base_url"] for key, told in row.tuning.items() if key.endswith("/openai")}
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


def test_a_named_ollama_model_thinks_and_another_judges_each_priced_at_nothing() -> None:
    """`local/<model>` per stage: the thinking, the judge and the caller each on their own model, all through Ollama."""
    chosen = models.Choices(
        llm="local/qwen3:30b-a3b-instruct-2507-q4_K_M", judge="local/gemma4:12b", caller="local/gemma4:e4b"
    )
    row = row_of(chosen)
    assert row.defaults[Stage.llm].model == "qwen3:30b-a3b-instruct-2507-q4_K_M"
    assert row.judge is not None and row.judge.llm.vendor == "openai" and row.judge.llm.model == "gemma4:12b"
    assert row.caller is not None and row.caller.llm is not None and row.caller.llm.model == "gemma4:e4b"
    assert row.tuning["llm/openai"].options["base_url"] == "http://127.0.0.1:11434/v1"
    assert {"qwen3:30b-a3b-instruct-2507-q4_K_M", "gemma4:12b", "gemma4:e4b"} <= set(row.rates)
    assert chosen.local_models == ("qwen3:30b-a3b-instruct-2507-q4_K_M", "gemma4:12b", "gemma4:e4b")


def test_a_mix_keeps_the_local_stages_servers_and_names_the_vendors_bare() -> None:
    """Anthropic thinks and, unasked, judges; the local ears keep base_url and Smart Turn, the voice its voices."""
    row = row_of(models.Choices(stt=models.LOCAL, turn="smart-turn", llm="anthropic", tts=models.LOCAL))
    assert row.defaults[Stage.llm].vendor == "anthropic" and row.defaults[Stage.llm].model is None
    assert "llm/openai" not in row.tuning and "stt/openai" in row.tuning and "tts/openai" in row.tuning
    assert row.judge is not None and row.judge.llm.vendor == "anthropic"
    assert row.caller is not None and row.caller.llm is not None and row.caller.llm.vendor == "anthropic"
    assert row.voices == {"openai/es": "ef_dora", "openai/en": "af_heart"}


def test_a_local_judge_beside_a_vendors_thinking_brings_ollamas_tuning() -> None:
    """The thinking on a vendor, the judge local: the judge's plugin still needs its base_url."""
    row = row_of(models.Choices(llm="anthropic", judge="local"))
    assert row.defaults[Stage.llm].vendor == "anthropic"
    assert row.judge is not None and row.judge.llm.model == models.LOCAL_LLM
    assert row.tuning["llm/openai"].options["base_url"] == "http://127.0.0.1:11434/v1"


def test_every_stage_on_a_vendor_leaves_the_ears_own_endpointing_and_the_embedder_local() -> None:
    """No turn model when the ears end the turn; no voices listed for a vendor; bge-m3 stays for memory and bases."""
    row = row_of(models.ALL_KEYS)
    assert {stage: one.vendor for stage, one in row.defaults.items()} == {
        "stt": "deepgram",
        "llm": "anthropic",
        "tts": "cartesia",
    }
    # The ears named bare are the plugin's own, as before: nothing is told of them vendor-wide.
    assert row.options_for(Stage.stt, "deepgram") is None and row.voices == {}
    assert all(plugins.is_installed(read_stage_key(key)[1]) for key in row.tuning)
    assert row.embedding is not None and row.embedding.url == "http://127.0.0.1:11434/v1"
    livekit = row_of(models.Choices(stt="deepgram", turn="livekit", llm="anthropic", tts="cartesia"))
    assert livekit.tuning["stt/deepgram"].turn_model == "v1-mini"


def test_the_row_carries_the_list_prices_the_package_ships() -> None:
    """A call on a vendor's key is priced from the first: the shipped list prices are the row's, open models free."""
    row = row_of(models.ALL_KEYS)
    shipped = list_prices()
    assert shipped and set(shipped) <= set(row.rates)
    assert row.rates["nova-3"].audio_seconds == shipped["nova-3"].audio_seconds
    local = row_of(models.ALL_LOCAL)
    assert local.rates[models.LOCAL_LLM].input == 0


def every_vendor_installed(monkeypatch: pytest.MonkeyPatch, *only: str) -> None:
    """An install that carries every vendor's plugin, or these alone."""

    def carried(vendor: str) -> bool:
        return not only or vendor in only

    monkeypatch.setattr(plugins, "is_installed", carried)


def test_a_new_machine_is_told_how_each_vendor_builds_the_models_it_is_offered(monkeypatch: pytest.MonkeyPatch) -> None:
    """Gemini's voice and Deepgram's Flux run on classes of their own: the row says which, by the family of model."""
    every_vendor_installed(monkeypatch)
    row = row_of(models.ALL_KEYS)
    voice = row.options_for(Stage.tts, "google", "gemini-3.8-flash-lite-tts")
    assert voice is not None and voice.builds == "beta.GeminiTTS"
    flux = row.options_for(Stage.stt, "deepgram", "flux-general-multi")
    assert flux is not None and (flux.builds, flux.ends_the_turn) == ("STTv2", True)
    one_language = row.options_for(Stage.stt, "deepgram", "flux-general-en")
    assert one_language is not None and one_language.options == {"language_hint": []}
    # Another model of the same vendor, and the vendor named bare, are the plugin's own class.
    assert row.options_for(Stage.stt, "deepgram", "nova-3") is None
    scribe = row.options_for(Stage.stt, "elevenlabs", "scribe_v2_realtime")
    assert scribe is not None and scribe.commits_when_told
    thinking = row.options_for(Stage.llm, "google", "gemini-3.8-flash")
    assert thinking is not None and thinking.request == {"thinking_config": {"thinking_level": "low"}}


def test_a_vendor_this_install_does_not_carry_is_told_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """A row naming a vendor nobody installed is refused where it is written, so its lines are left out."""
    every_vendor_installed(monkeypatch, "anthropic")
    assert set(list_stage_options()) == {"llm/anthropic/claude-haiku-5-5"}


def test_a_detector_asked_for_takes_the_end_of_the_turn_from_ears_that_end_it(monkeypatch: pytest.MonkeyPatch) -> None:
    """AssemblyAI ends the turn itself; with livekit's detector asked for, the detector does and the ears do not."""
    every_vendor_installed(monkeypatch)
    theirs = row_of(models.Choices(stt="assemblyai", turn="stt", llm="anthropic", tts="cartesia"))
    assert theirs.tuning["stt/assemblyai"].ends_the_turn and theirs.tuning["stt/assemblyai"].turn_model is None
    asked = row_of(models.Choices(stt="assemblyai", turn="livekit", llm="anthropic", tts="cartesia"))
    assert (asked.tuning["stt/assemblyai"].ends_the_turn, asked.tuning["stt/assemblyai"].turn_model) == (
        False,
        "v1-mini",
    )
