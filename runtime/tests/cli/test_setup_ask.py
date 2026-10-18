"""What `setup` asks at a terminal: the machine, a stage at a time with what could run it, a key as it is picked."""

import dataclasses
from collections.abc import Iterator
from pathlib import Path

import pytest

from pinecall_runtime.cli import setup_ask as ask
from pinecall_runtime.cli import setup_models as models
from pinecall_runtime.providers import service as providers
from pinecall_runtime.providers.service.machine import Card

A_MAC = providers.Machine(
    system="darwin",
    arch="arm64",
    cores=10,
    ram_gib=32.0,
    cards=(),
    apple_silicon=True,
    docker=True,
    ollama_here=True,
    ollama_models=("bge-m3:latest", "gemma4:12b", "qwen3.8:27b"),
    keys_found={},
)


def answers(*lines: str) -> ask.Read:
    """What the person types, line after line; each question shown as a terminal shows it."""
    given: Iterator[str] = iter(lines)

    def read(message: str) -> str:
        print(message)
        return next(given)

    return read


def test_the_panel_is_one_line_saying_what_the_machine_is() -> None:
    """A Mac: its unified memory and the models' share; Docker; Ollama and the models it holds."""
    fits = providers.recommend(A_MAC)
    assert ask.panel(A_MAC, fits) == (
        "\n  this machine   Apple silicon · 32.0 GB unified — 22.5 GB for the models"
        " · Docker ✓ · Ollama ✓ (bge-m3:latest, gemma4:12b, qwen3.8:27b)"
    )
    box = dataclasses.replace(A_MAC, apple_silicon=False, docker=False, ollama_here=False, ollama_models=())
    assert "no GPU · 32.0 GB RAM · 10 cores · Docker ✗ (needed) · Ollama ✗" in ask.panel(box, providers.recommend(box))
    a100 = dataclasses.replace(box, cards=(Card("NVIDIA A100", 40.0),))
    assert "NVIDIA A100 · 40.0 GB — 34.2 GB for the models beside the voice" in ask.panel(
        a100, providers.recommend(a100)
    )


def test_a_stages_options_are_the_open_models_here_then_every_vendor_doing_it(tmp_path: Path) -> None:
    """The thinking: each measured model (fits or short), Ollama's other tags, the vendors with where each key is."""
    fits = providers.recommend(A_MAC)
    (tmp_path / ".zshrc").write_text("export ACME_API_KEY=ak-x\n", encoding="utf-8")
    thinking = ask.options_for("llm", models.recommended(fits), A_MAC, fits, environ={}, home=tmp_path)
    choices = [one.choice for one in thinking]
    assert choices[:3] == [
        "local/nemotron-3.5-lightning:30b-a3b",
        "local/gemma4:12b",
        "local/gemma4:e4b",
    ]
    assert thinking[0].said == "Ollama · short by 2.5 GB"
    assert thinking[1].said == "Ollama · fits · 0.90 s to first token"
    # The embedder Ollama holds is never offered to think.
    assert choices[3] == "local/qwen3.8:27b" and thinking[3].said == "Ollama · pulled already"
    assert "local/bge-m3:latest" not in choices
    acme = next(one for one in thinking if one.choice == "acme")
    assert acme.said == "ACME_API_KEY in ~/.zshrc" and acme.missing is None
    installed = {
        name for name, vendor in providers.installed().items() if vendor.broken is None and "llm" in vendor.does
    }
    assert {one.choice for one in thinking if not one.choice.startswith("local")} == installed
    # Nowhere: the option says the key is asked the moment it is picked.
    nowhere = ask.options_for("tts", models.recommended(fits), A_MAC, fits, environ={}, home=tmp_path / "none")
    assert nowhere[0] == ask.Option("local", "Kokoro, on this machine")
    acme_voice = next(one for one in nowhere if one.choice == "acme")
    assert acme_voice == ask.Option("acme", "ACME_API_KEY — asked now if you pick it", missing="ACME_API_KEY")
    ears = ask.options_for("stt", models.recommended(fits), A_MAC, fits, environ={"ACME_API_KEY": "x"}, home=tmp_path)
    assert ears[0] == ask.Option("local", "Whisper large-v3 turbo, on this machine")
    assert next(one for one in ears if one.choice == "acme").said == "ACME_API_KEY in the environment"
    # The local ears end no turn: that choice is not offered.
    turns = ask.options_for("turn", models.recommended(fits), A_MAC, fits)
    assert [one.choice for one in turns] == ["smart-turn", "livekit"]


def test_enter_takes_every_default_and_the_stack_is_said_before_it_runs(capsys: pytest.CaptureFixture[str]) -> None:
    """Six Enters and one more: the recommended stack, nothing typed, no key asked."""
    fits = providers.recommend(A_MAC)
    chosen, typed = ask.chosen(
        A_MAC, fits, models.recommended(fits), environ={}, home=Path("/nowhere"), read=answers(*[""] * 7)
    )
    assert chosen == models.Choices(llm="local/gemma4:12b") and typed == {}
    shown = capsys.readouterr().out
    assert "ears — who hears the caller" in shown and "1  local" in shown and "recommended" in shown
    assert "judge — who judges a finished call   [the thinking's: local/gemma4:12b]:" in shown
    assert "caller — who plays the simulated caller   [the thinking's: local/gemma4:12b]:" in shown
    assert (
        "the stack\n    ears local · turn smart-turn · thinking local/gemma4:12b · voice local"
        " · judge local/gemma4:12b · caller local/gemma4:12b" in shown
    )


def test_a_vendor_picked_without_a_key_is_asked_for_it_there_and_one_found_is_read(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The thinking picked onto a vendor whose key is nowhere: asked once, kept; the voice onto one in ~/.zshrc."""
    fits = providers.recommend(A_MAC)
    base = models.recommended(fits)
    (tmp_path / ".zshrc").write_text("export ACME_API_KEY=ak-x\n", encoding="utf-8")
    chosen, typed = ask.chosen(
        A_MAC,
        fits,
        base,
        environ={},
        home=tmp_path / "none",
        read=answers("", "", "acme", "", "", "", ""),
        hidden=lambda v: f"typed-{v}",
    )
    assert chosen.llm == "acme" and chosen.judging == "acme" and typed == {"ACME_API_KEY": "typed-ACME_API_KEY"}
    found, read = ask.chosen(A_MAC, fits, base, environ={}, home=tmp_path, read=answers("", "", "", "acme", "", "", ""))
    assert found.tts == "acme" and read == {}
    assert "ACME_API_KEY read from ~/.zshrc" in capsys.readouterr().out
    # A judge named apart from the thinking stands on its own; the caller still follows.
    judged, _ = ask.chosen(A_MAC, fits, base, environ={}, home=tmp_path, read=answers("", "", "", "", "acme", "", ""))
    assert judged.judge == "acme" and judged.caller is None and judged.calling == "local/gemma4:12b"


def test_an_answer_that_is_none_of_them_is_said_and_asked_again(capsys: pytest.CaptureFixture[str]) -> None:
    """A number out of range or a name not listed is refused by name; the stage is asked again."""
    fits = providers.recommend(A_MAC)
    chosen, _ = ask.chosen(
        A_MAC,
        fits,
        models.recommended(fits),
        environ={},
        home=Path("/nowhere"),
        read=answers("9", "nobody", "", "", "", "", "", "", ""),
    )
    assert chosen.stt == "local"
    shown = capsys.readouterr().out
    assert "'9' is none of them: a number from 1 to" in shown and "'nobody' is none of them" in shown


def test_a_number_on_the_judges_line_shows_the_thinkings_list(capsys: pytest.CaptureFixture[str]) -> None:
    """The judge follows the thinking on one line; a number there lists what could judge, and one is picked from it."""
    fits = providers.recommend(A_MAC)
    base = models.recommended(fits)
    chosen, _ = ask.chosen(
        A_MAC, fits, base, environ={}, home=Path("/nowhere"), read=answers("", "", "", "", "3", "3", "", "")
    )
    assert chosen.judge == "local/gemma4:e4b" and chosen.caller is None
    shown = capsys.readouterr().out
    assert "\n  judge — who judges a finished call\n    1  local/nemotron" in shown


def test_a_list_holds_what_runs_with_nothing_asked_and_the_usual_vendor(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A vendor whose key is found is listed; one with no key is in the one line of the rest, and its name picks it."""
    fits = providers.recommend(A_MAC)
    base = models.recommended(fits)
    (tmp_path / ".zshrc").write_text("export ACME_API_KEY=ak-x\n", encoding="utf-8")
    ask.chosen(A_MAC, fits, base, environ={}, home=tmp_path, read=answers(*[""] * 7))
    found = capsys.readouterr().out
    ears = found.split("ears — who hears the caller")[1].split("ears [1]")[0]
    assert "acme" in ears and "ACME_API_KEY in ~/.zshrc" in ears
    ask.chosen(A_MAC, fits, base, environ={}, home=tmp_path / "none", read=answers(*[""] * 7))
    nowhere = capsys.readouterr().out.split("ears — who hears the caller")[1].split("ears [1]")[0]
    listed = [line.split()[1] for line in nowhere.strip().splitlines() if line.strip()[0].isdigit()]
    assert listed[0] == "local" and "acme" not in listed
    assert "more:" in nowhere and "— type a name, Tab completes" in nowhere
