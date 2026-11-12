"""The vendors' keys `setup` runs on: found in the environment or a shell file, else asked; what it says of them."""

from pathlib import Path

import pytest

from runtime.cli.setup import choices as models
from runtime.cli.setup import keys as found_keys
from runtime.exceptions import ValidationError
from runtime.providers.service import machine


def test_the_keys_a_mix_needs_and_where_each_came_from(tmp_path: Path) -> None:
    """One key per vendor of yours: the environment, else a shell file, else typed; the local word for openai always."""
    environ = {"ANTHROPIC_API_KEY": "sk-ant-x"}
    (tmp_path / ".zshrc").write_text("export ACME_API_KEY=ak-x\n", encoding="utf-8")
    mixed = models.Choices(stt=models.LOCAL, llm="anthropic", tts="acme")
    given, found = found_keys.keys_for(mixed, ask=None, environ=environ, home=tmp_path)
    assert given == {"acme": "ak-x", "anthropic": "sk-ant-x", "openai": "local"}
    assert found == {"ACME_API_KEY": "~/.zshrc", "ANTHROPIC_API_KEY": "the environment"}
    assert machine.key_variable("assemblyai") == "ASSEMBLYAI_API_KEY"
    # A judge on a vendor of yours needs that vendor's key as the thinking would.
    judged, _ = found_keys.keys_for(models.Choices(judge="anthropic"), ask=None, environ=environ, home=tmp_path)
    assert judged == {"anthropic": "sk-ant-x", "openai": "local"}
    # Nowhere, at a terminal: asked once; with nobody to ask, refused naming the variable.
    typed, where = found_keys.keys_for(
        models.Choices(tts="acme"), ask=lambda _v: " ak-typed ", environ={}, home=tmp_path / "x"
    )
    assert typed["acme"] == "ak-typed" and where == {"ACME_API_KEY": "typed"}
    with pytest.raises(ValidationError, match="acme needs a key: set ACME_API_KEY"):
        found_keys.keys_for(models.Choices(tts="acme"), ask=None, environ={}, home=tmp_path / "x")
    # A shell line that expands is found but not read: asked as if it were nowhere.
    (tmp_path / ".zshrc").write_text("export ACME_API_KEY=$(cat ~/k)\n", encoding="utf-8")
    with pytest.raises(ValidationError, match="acme needs a key"):
        found_keys.keys_for(models.Choices(tts="acme"), ask=None, environ={}, home=tmp_path)


def test_every_key_found_is_loaded_and_where_it_was_said(tmp_path: Path) -> None:
    """A vendor whose key is in the environment or a shell file is loaded; one that expands or is nowhere is not."""
    (tmp_path / ".zshrc").write_text("export ACME_API_KEY='ak-z'\n", encoding="utf-8")
    loaded, places = found_keys.keys_found(environ={}, home=tmp_path)
    assert loaded["acme"] == "ak-z" and places["ACME_API_KEY"] == "~/.zshrc"
    assert (
        found_keys.say_keys(loaded, places, server=False) == "  keys      acme — found in ~/.zshrc, lent to your orgs"
    )
    from_env, said = found_keys.keys_found(environ={"ACME_API_KEY": "ak-e"}, home=tmp_path)
    assert from_env["acme"] == "ak-e" and said["ACME_API_KEY"] == machine.THE_ENVIRONMENT
    (tmp_path / ".zshrc").write_text('export ACME_API_KEY="$(op read acme)"\n', encoding="utf-8")
    expands, _ = found_keys.keys_found(environ={}, home=tmp_path)
    assert "acme" not in expands


def test_the_lines_setup_says_name_the_keys_and_the_open_models() -> None:
    """The vendors with a key, where they were and that they are lent; the open models served, or none."""
    found = {"A": machine.THE_ENVIRONMENT, "B": "~/.zshrc"}
    assert found_keys.say_keys({"xai": "k", "cartesia": "k"}, found, server=True) == (
        f"  keys      cartesia · xai — found in {machine.THE_ENVIRONMENT} and ~/.zshrc, lent to every org"
    )
    assert found_keys.say_keys({}, {}, server=False) == (
        "  keys      none found — `pinecall providers add <vendor>` adds one"
    )
    assert found_keys.say_models(models.Choices(llm="local/gemma4:12b")) == (
        "  models    gemma4:12b · whisper · kokoro — open, served here"
    )
    assert found_keys.say_models(models.ALL_LOCAL, card=True).endswith("served here on the GPU")
    assert found_keys.say_models(models.ALL_KEYS) == "  models    none served here — calls run on the keys above"
