"""The row `setup` writes for each mix of local stages and vendors: defaults, tuning, judge, caller, rates."""

from pinecall_runtime.cli import setup_models as models
from pinecall_runtime.cli.setup_row import list_prices, row_of


def test_every_stage_local_names_the_three_servers_on_loopback() -> None:
    """Every stage on the openai plugin, each with its server's base_url; Smart Turn ends the turn; nothing priced."""
    row = row_of(models.ALL_LOCAL)
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


def test_a_named_ollama_model_thinks_and_another_judges_each_priced_at_nothing() -> None:
    """`local/<model>` per stage: the thinking, the judge and the caller each on their own model, all through Ollama."""
    chosen = models.Choices(
        llm="local/qwen3:30b-a3b-instruct-2507-q4_K_M", judge="local/gemma4:12b", caller="local/gemma4:e4b"
    )
    row = row_of(chosen)
    assert row.defaults["llm"].model == "qwen3:30b-a3b-instruct-2507-q4_K_M"
    assert row.judge is not None and row.judge.llm.vendor == "openai" and row.judge.llm.model == "gemma4:12b"
    assert row.caller is not None and row.caller.llm is not None and row.caller.llm.model == "gemma4:e4b"
    assert row.tuning["llm/openai"].options["base_url"] == "http://127.0.0.1:11434/v1"
    assert {"qwen3:30b-a3b-instruct-2507-q4_K_M", "gemma4:12b", "gemma4:e4b"} <= set(row.rates)
    assert chosen.local_models == ("qwen3:30b-a3b-instruct-2507-q4_K_M", "gemma4:12b", "gemma4:e4b")


def test_a_mix_keeps_the_local_stages_servers_and_names_the_vendors_bare() -> None:
    """Anthropic thinks and, unasked, judges; the local ears keep base_url and Smart Turn, the voice its voices."""
    row = row_of(models.Choices(stt=models.LOCAL, turn="smart-turn", llm="anthropic", tts=models.LOCAL))
    assert row.defaults["llm"].vendor == "anthropic" and row.defaults["llm"].model is None
    assert "llm/openai" not in row.tuning and "stt/openai" in row.tuning and "tts/openai" in row.tuning
    assert row.judge is not None and row.judge.llm.vendor == "anthropic"
    assert row.caller is not None and row.caller.llm is not None and row.caller.llm.vendor == "anthropic"
    assert row.voices == {"openai/es": "ef_dora", "openai/en": "af_heart"}


def test_a_local_judge_beside_a_vendors_thinking_brings_ollamas_tuning() -> None:
    """The thinking on a vendor, the judge local: the judge's plugin still needs its base_url."""
    row = row_of(models.Choices(llm="anthropic", judge="local"))
    assert row.defaults["llm"].vendor == "anthropic"
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
    assert row.tuning == {} and row.voices == {}
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
