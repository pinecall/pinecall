"""The vendors' keys `setup` runs on: found in the environment or a shell file, else asked; what it says of them."""

from pathlib import Path

import pytest

from runtime.cli.setup import choices as models
from runtime.cli.setup import keys as found_keys
from runtime.exceptions import ValidationError
from runtime.providers.service import machine


async def typed_at_a_terminal(_variable: str) -> str:
    return " ak-typed "


async def test_the_keys_a_mix_needs_and_where_each_came_from(tmp_path: Path) -> None:
    """One key per vendor of yours: the environment, else a shell file, else typed; the local word for openai always."""
    environ = {"ANTHROPIC_API_KEY": "sk-ant-x"}
    (tmp_path / ".zshrc").write_text("export ACME_API_KEY=ak-x\n", encoding="utf-8")
    mixed = models.Choices(stt=models.LOCAL, llm="anthropic", tts="acme")
    given, found = await found_keys.keys_for(mixed, ask=None, environ=environ, home=tmp_path)
    assert given == {"acme": "ak-x", "anthropic": "sk-ant-x", "openai": "local"}
    assert found == {"ACME_API_KEY": "~/.zshrc", "ANTHROPIC_API_KEY": "the environment"}
    assert machine.key_variable("assemblyai") == "ASSEMBLYAI_API_KEY"
    # A judge on a vendor of yours needs that vendor's key as the thinking would.
    judged, _ = await found_keys.keys_for(models.Choices(judge="anthropic"), ask=None, environ=environ, home=tmp_path)
    assert judged == {"anthropic": "sk-ant-x", "openai": "local"}
    # Nowhere, at a terminal: asked once; with nobody to ask, refused naming the variable.
    typed, where = await found_keys.keys_for(
        models.Choices(tts="acme"), ask=typed_at_a_terminal, environ={}, home=tmp_path / "x"
    )
    assert typed["acme"] == "ak-typed" and where == {"ACME_API_KEY": "typed"}
    with pytest.raises(ValidationError, match="acme needs a key: set ACME_API_KEY"):
        await found_keys.keys_for(models.Choices(tts="acme"), ask=None, environ={}, home=tmp_path / "x")
    # A shell line that expands is found but not read: asked as if it were nowhere.
    (tmp_path / ".zshrc").write_text("export ACME_API_KEY=$(cat ~/k)\n", encoding="utf-8")
    with pytest.raises(ValidationError, match="acme needs a key"):
        await found_keys.keys_for(models.Choices(tts="acme"), ask=None, environ={}, home=tmp_path)


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


def test_a_person_who_came_with_no_key_reads_what_is_asked_of_them_and_why(tmp_path: Path) -> None:
    """Before the first key is asked for: how many, what each vendor does in a call, and the way with one alone."""
    on_vendors = models.Choices(stt=models.LOCAL, llm="anthropic", tts="acme")
    said = found_keys.say_asked(on_vendors, environ={}, home=tmp_path)
    assert said is not None
    asking, chat_only = said.split("\n")
    assert asking == "  asking    2 keys found nowhere — acme speaks · anthropic thinks: typed below, nothing shown"
    assert chat_only.strip() == "written calls alone need the one that thinks: pinecall-runtime setup --chat-only"
    assert found_keys.say_models(models.ALL_KEYS, keyed=False) == (
        "  models    none served here — calls run on a vendor's key for each stage"
    )
    # One key missing is asked for with no word about another way; none missing, nothing is said.
    thinking_found = {"ANTHROPIC_API_KEY": "sk-ant-x"}
    assert found_keys.say_asked(on_vendors, environ=thinking_found, home=tmp_path) == (
        "  asking    1 key found nowhere — acme speaks: typed below, nothing shown"
    )
    both_found = {**thinking_found, "ACME_API_KEY": "ak-x"}
    assert found_keys.say_asked(on_vendors, environ=both_found, home=tmp_path) is None
    assert found_keys.say_asked(models.ALL_LOCAL, environ={}, home=tmp_path) is None
    # A vendor that plays two parts is said with both; the judge and the caller it also plays are not repeated.
    one_for_two = models.Choices(stt=models.LOCAL, llm="acme", tts="acme")
    assert found_keys.say_asked(one_for_two, environ={}, home=tmp_path) == (
        "  asking    1 key found nowhere — acme thinks and speaks: typed below, nothing shown"
    )
