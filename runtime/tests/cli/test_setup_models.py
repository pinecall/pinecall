"""What `setup` runs a call on: a choice per stage, local or a vendor's, the judge, the caller, the keys, the turn."""

from pathlib import Path

import pytest

from pinecall_runtime.cli import setup_models as models
from pinecall_runtime.exceptions import ValidationError
from pinecall_runtime.providers import service as providers


def test_a_choice_is_local_a_local_model_or_a_vendor_with_or_without_its_model() -> None:
    """`local`, `local/gemma4:12b`, `hf/Qwen/Qwen2.5-3B-Instruct` and a bare `anthropic` each read as what they name."""
    assert models.is_local("local") and models.is_local("local/gemma4:12b") and not models.is_local("anthropic")
    assert (models.vendor_of("hf/Qwen/Qwen2.5-3B-Instruct"), models.model_of("hf/Qwen/Qwen2.5-3B-Instruct")) == (
        "hf",
        "Qwen/Qwen2.5-3B-Instruct",
    )
    assert (models.vendor_of("anthropic"), models.model_of("anthropic")) == ("anthropic", None)
    # A vendor's name is lowered; a model's case is the registry's.
    assert models.local_or_vendor(" Local/Qwen3:8B ") == "local/Qwen3:8B"
    assert models.local_or_vendor("Anthropic") == "anthropic"


def test_the_judge_and_the_caller_follow_the_thinking_unless_named() -> None:
    """Unnamed, both run on the thinking's model; named, each on its own; Ollama pulls each local model once."""
    chosen = models.Choices(llm="local/gemma4:12b")
    assert (chosen.judging, chosen.calling) == ("local/gemma4:12b", "local/gemma4:12b")
    assert chosen.local_models == ("gemma4:12b",)
    mixed = models.Choices(llm="anthropic", judge="local/gemma4:e4b", caller="local")
    assert (mixed.judging, mixed.calling) == ("local/gemma4:e4b", "local")
    assert mixed.local_models == ("gemma4:e4b", models.LOCAL_LLM)
    assert mixed.vendors == frozenset({"anthropic"})
    assert models.Choices(llm="local", judge="local/gemma4:e4b", caller="local/gemma4:e4b").local_models == (
        models.LOCAL_LLM,
        "gemma4:e4b",
    )


def test_the_keys_a_mix_needs_and_where_each_came_from(tmp_path: Path) -> None:
    """One key per vendor of yours: the environment, else a shell file, else typed; the local word for openai always."""
    environ = {"ANTHROPIC_API_KEY": "sk-ant-x"}
    (tmp_path / ".zshrc").write_text("export ACME_API_KEY=ak-x\n", encoding="utf-8")
    mixed = models.Choices(stt=models.LOCAL, llm="anthropic", tts="acme")
    given, found = models.keys_for(mixed, ask=None, environ=environ, home=tmp_path)
    assert given == {"acme": "ak-x", "anthropic": "sk-ant-x", "openai": "local"}
    assert found == {"ACME_API_KEY": "~/.zshrc", "ANTHROPIC_API_KEY": "the environment"}
    assert providers.key_variable("assemblyai") == "ASSEMBLYAI_API_KEY"
    # A judge on a vendor of yours needs that vendor's key as the thinking would.
    judged, _ = models.keys_for(models.Choices(judge="anthropic"), ask=None, environ=environ, home=tmp_path)
    assert judged == {"anthropic": "sk-ant-x", "openai": "local"}
    # Nowhere, at a terminal: asked once; with nobody to ask, refused naming the variable.
    typed, where = models.keys_for(
        models.Choices(tts="acme"), ask=lambda _v: " ak-typed ", environ={}, home=tmp_path / "x"
    )
    assert typed["acme"] == "ak-typed" and where == {"ACME_API_KEY": "typed"}
    with pytest.raises(ValidationError, match="acme needs a key: set ACME_API_KEY"):
        models.keys_for(models.Choices(tts="acme"), ask=None, environ={}, home=tmp_path / "x")
    # A shell line that expands is found but not read: asked as if it were nowhere.
    (tmp_path / ".zshrc").write_text("export ACME_API_KEY=$(cat ~/k)\n", encoding="utf-8")
    with pytest.raises(ValidationError, match="acme needs a key"):
        models.keys_for(models.Choices(tts="acme"), ask=None, environ={}, home=tmp_path)


def test_the_turn_is_one_of_three_and_the_local_ears_cannot_end_it() -> None:
    """Whisper has no endpointing of its own: `stt` as the turn is refused naming the two that work."""
    with pytest.raises(ValidationError, match="--turn is one of stt, smart-turn, livekit"):
        models.turn_of("vad")
    assert models.turn_of(" Smart-Turn ") == "smart-turn"
    with pytest.raises(ValidationError, match="the local ears \\(Whisper\\) end no turn themselves"):
        models.check_choices(models.Choices(turn="stt"))


def test_what_is_checked_a_vendor_installed_doing_its_stage_and_one_local_voice() -> None:
    """A judge on a vendor nobody installed is refused as the thinking would be; the local voice takes no model."""
    with pytest.raises(ValidationError, match="no vendor named 'nobody'"):
        models.check_choices(models.Choices(judge="nobody"))
    with pytest.raises(ValidationError, match="the local voice is Kokoro"):
        models.check_choices(models.Choices(tts="local/piper"))
    assert models.check_choices(models.Choices(llm="local/gemma4:12b", caller="acme")).calling == "acme"


def test_every_key_found_is_loaded_and_where_it_was_said(tmp_path: Path) -> None:
    """A vendor whose key is in the environment or a shell file is loaded; one that expands or is nowhere is not."""
    (tmp_path / ".zshrc").write_text("export ACME_API_KEY='ak-z'\n", encoding="utf-8")
    loaded, places = models.keys_found(environ={}, home=tmp_path)
    assert loaded["acme"] == "ak-z" and places["ACME_API_KEY"] == "~/.zshrc"
    assert models.said_loading(places) == "loading providers from ~/.zshrc …"
    assert "acme" in models.said_providers(loaded)
    from_env, said = models.keys_found(environ={"ACME_API_KEY": "ak-e"}, home=tmp_path)
    assert from_env["acme"] == "ak-e" and said["ACME_API_KEY"] == providers.THE_ENVIRONMENT
    (tmp_path / ".zshrc").write_text('export ACME_API_KEY="$(op read acme)"\n', encoding="utf-8")
    expands, _ = models.keys_found(environ={}, home=tmp_path)
    assert "acme" not in expands


def test_the_lines_setup_says_name_the_providers_and_the_open_models() -> None:
    """The providers with a key, counted; the open models this machine serves, or none on a stack of vendors."""
    assert models.said_providers({"xai": "k", "cartesia": "k"}) == "providers  cartesia · xai — 2 keys found"
    assert models.said_providers({"xai": "k"}) == "providers  xai — 1 key found"
    assert models.said_providers({}) == "providers  no keys found: `pinecall providers add <vendor>` adds one"
    assert models.said_loading({"A": providers.THE_ENVIRONMENT, "B": "~/.zshrc", "C": "~/.bashrc"}) == (
        f"loading providers from {providers.THE_ENVIRONMENT} and ~/.bashrc and ~/.zshrc …"
    )
    assert models.said_models(models.Choices(llm="local/gemma4:12b")) == (
        "models     gemma4:12b · whisper · kokoro — open, served on this machine"
    )
    assert models.said_models(models.ALL_KEYS) == "models     none served here: an agent runs on the providers"
