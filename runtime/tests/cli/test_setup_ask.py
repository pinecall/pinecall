"""What `setup` shows at a terminal: the machine, the measured models, the stack and what runs each stage."""

import dataclasses
from pathlib import Path

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
    ollama_models=("bge-m3", "gemma4:12b"),
    keys_found={"anthropic": "~/.zshrc"},
)


def test_the_panel_says_what_the_machine_is_and_which_measured_models_fit() -> None:
    """A Mac: its unified memory and the models' share; Docker and Ollama with its models; what fits, what is short."""
    fits = providers.recommend(A_MAC)
    shown = ask.panel(A_MAC, fits)
    assert "Apple silicon · 32.0 GB unified — 22.5 GB for the models" in shown
    assert "Docker ✓ · Ollama ✓ (bge-m3, gemma4:12b)" in shown
    assert "gemma4:12b" in shown and "fits" in shown
    assert "nemotron-3.5-lightning:30b-a3b" in shown and "short by" in shown
    assert "0.45 s to first token · tool called 18/18" in shown
    assert "unmeasured" in shown
    box = dataclasses.replace(A_MAC, apple_silicon=False, docker=False, ollama_here=False, ollama_models=())
    plain = ask.panel(box, providers.recommend(box))
    assert "no GPU · 32.0 GB RAM · 10 cores" in plain and "Docker ✗ (needed) · Ollama ✗" in plain
    a100 = dataclasses.replace(box, cards=(Card("NVIDIA A100", 40.0),))
    assert "NVIDIA A100 · 40.0 GB — 34.2 GB for the models beside the voice" in ask.panel(
        a100, providers.recommend(a100)
    )


def test_the_stack_names_what_runs_each_stage_and_where_a_vendors_key_is(tmp_path: Path) -> None:
    """Local stages say their server; a vendor says its variable and where it was found, or that it will be asked."""
    fits = providers.recommend(A_MAC)
    local = ask.stack(models.recommended(fits), fits, environ={}, home=tmp_path)
    assert "ears      local" in local and "Whisper (" in local and "on this machine" in local
    assert "turn      smart-turn" in local and "Smart Turn v3, on the worker's CPU" in local
    assert "thinking  local/gemma4:12b" in local and "Ollama, 0.90 s to first token" in local
    assert "voice     local" in local and "Kokoro, on this machine" in local
    assert "judge     the thinking's model" in local and "caller    the thinking's model" in local
    (tmp_path / ".zshrc").write_text("export ACME_API_KEY=ak-x\n", encoding="utf-8")
    mixed = models.Choices(stt="acme", turn="stt", llm="acme", judge="local/gemma4:12b")
    vendors = ask.stack(mixed, fits, environ={}, home=tmp_path)
    assert "ACME_API_KEY in ~/.zshrc" in vendors and "ak-x" not in vendors
    assert "the ears' own endpointing" in vendors
    assert "judge     local/gemma4:12b" in vendors
    nowhere = ask.stack(models.Choices(tts="acme"), fits, environ={}, home=tmp_path / "none")
    assert "ACME_API_KEY not found: asked when you press Enter" in nowhere
    exported = ask.stack(models.Choices(tts="acme"), fits, environ={"ACME_API_KEY": "sk-x"}, home=tmp_path / "none")
    assert "ACME_API_KEY in the environment" in exported and "sk-x" not in exported


def test_what_completes_a_stage_is_local_the_local_models_and_every_vendor_doing_it() -> None:
    """The thinking: `local`, Ollama's tags, the measured, the vendors; the ears: Whisper's model; the voice: Kokoro."""
    fits = providers.recommend(A_MAC)
    thinking = ask.words_for("llm", A_MAC, fits)
    assert thinking[:3] == ["local", "local/bge-m3", "local/gemma4:12b"]
    assert "local/nemotron-3.5-lightning:30b-a3b" in thinking and "local/gemma4:e4b" in thinking
    assert len(thinking) == len(set(thinking))
    installed = {name for name, vendor in providers.installed().items() if vendor.broken is None}
    assert all(word.startswith("local") or word in installed for word in thinking)
    assert ask.words_for("judge", A_MAC, fits) == thinking
    ears = ask.words_for("stt", A_MAC, fits)
    assert ears[:2] == ["local", f"local/{models.LOCAL_STT}"] and "local/gemma4:12b" not in ears
    assert (
        ask.words_for("tts", A_MAC, fits)[0] == "local"
        and len([w for w in ask.words_for("tts", A_MAC, fits) if w.startswith("local")]) == 1
    )
