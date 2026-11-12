"""What `setup --recommend` says: the machine as read, and the stack that fits it from what was measured."""

import dataclasses
from pathlib import Path

from runtime.enums import Stage
from runtime.providers.service import machine as machine_

THE_30B = "nemotron-3.5-lightning:30b-a3b"
# What was measured as the box keeps it: the 30B on an A100 (2026-10-18), the two Gemmas on an L4
# (2026-10-17), the voice's servers on the L4, and the vendors a machine with no GPU runs on.
MEASURED = machine_.Measured(
    models=(
        machine_.MeasuredModel(
            THE_30B, 25.0, 0.45, "tool called 18/18 on voice turns · written goldens 5/5 · spoken 2/3", "30B, 3B active"
        ),
        machine_.MeasuredModel("gemma4:12b", 9.0, 0.9, "message 3/3 · documents 3/3 · talk 3/3", "did everything"),
        machine_.MeasuredModel("gemma4:e4b", 7.5, 0.8, "message 2/3 · documents 3/3 · talk 3/3", "missed once"),
    ),
    on_keys={Stage.stt: "deepgram", Stage.llm: "anthropic", Stage.tts: "cartesia"},
    servers_gib={"whisper": 2.3, "kokoro": 1.1, "embedder": 0.9},
)
VENDORS = tuple(MEASURED.on_keys.values())


A_LINUX_BOX = machine_.Machine(
    system="linux",
    arch="x86_64",
    cores=8,
    ram_gib=32.0,
    cards=(),
    apple_silicon=False,
    docker=True,
    ollama_here=False,
    ollama_models=(),
    keys_found={},
)


def a_machine(**given: object) -> machine_.Machine:
    return dataclasses.replace(A_LINUX_BOX, **given)


def test_a_24_gb_card_runs_the_12b_beside_the_voice_and_a_40_gb_one_the_30b() -> None:
    """The budget is the card's memory less the ears, the voice, the embedder and a margin; the best that fits wins."""
    l4 = machine_.recommend(a_machine(cards=(machine_.Card("NVIDIA L4", 23.0),)), MEASURED)
    assert l4.on == "gpu" and l4.stack["llm"] == "local/gemma4:12b"
    assert l4.stack == {
        "stt": "local",
        "turn": "smart-turn",
        "llm": "local/gemma4:12b",
        "tts": "local",
        "judge": "local/gemma4:12b",
        "caller": "local/gemma4:12b",
    }
    big = next(one for one in l4.candidates if one.model == THE_30B)
    assert not big.fits and big.short_by_gib > 0
    assert "18/18" in big.did
    a100 = machine_.recommend(a_machine(cards=(machine_.Card("NVIDIA A100-SXM4-40GB", 40.0),)), MEASURED)
    assert a100.stack["llm"] == f"local/{THE_30B}" and a100.stack["judge"] == f"local/{THE_30B}"


def test_no_card_means_the_vendors_keys_and_says_which_are_set_and_where() -> None:
    """A machine with no GPU is told the measured models need one; its stack is the three vendors, each key placed."""
    cpu = machine_.recommend(a_machine(keys_found={"deepgram": "~/.zshrc"}), MEASURED)
    assert cpu.on == "cpu" and cpu.budget_gib == 0
    assert cpu.stack == {
        "stt": "deepgram",
        "llm": "anthropic",
        "tts": "cartesia",
        "turn": "stt",
        "judge": "anthropic",
        "caller": "anthropic",
    }
    assert cpu.keys["stt"] == {"vendor": "deepgram", "variable": "DEEPGRAM_API_KEY", "found": True, "where": "~/.zshrc"}
    assert cpu.keys["llm"]["found"] is False and cpu.keys["llm"]["where"] is None
    assert any("no GPU" in note for note in cpu.notes)
    assert all(not one.fits for one in cpu.candidates)


def test_a_mac_counts_three_quarters_of_its_memory_and_runs_the_voice_on_its_cpu() -> None:
    """Apple silicon: Ollama on Metal gets most of the unified memory; the containers' CPU images are unmeasured."""
    mac = machine_.recommend(a_machine(system="darwin", arch="arm64", ram_gib=48.0, apple_silicon=True), MEASURED)
    assert mac.on == "apple" and mac.budget_gib == 36.0
    assert mac.stack["llm"] == f"local/{THE_30B}"
    assert any("unmeasured" in note for note in mac.notes)
    assert machine_.recommend(
        a_machine(system="darwin", arch="arm64", ram_gib=32.0, apple_silicon=True), MEASURED
    ).stack["llm"] == ("local/gemma4:12b")
    small = machine_.recommend(a_machine(system="darwin", arch="arm64", ram_gib=8.0, apple_silicon=True), MEASURED)
    assert small.stack["llm"] == "anthropic" and small.stack["stt"] == "local"


def test_the_machine_is_read_off_nvidia_smi_the_environment_and_the_shells_files(tmp_path: Path) -> None:
    """Cards parsed from nvidia-smi's CSV; each key's place by vendor, the environment first; values never kept."""

    def fake(command: list[str]) -> str | None:
        if command[0] == "nvidia-smi":
            return "NVIDIA L4, 23034\nNVIDIA L4, 23034\n"
        return None

    (tmp_path / ".zshrc").write_text(
        'export CARTESIA_API_KEY="ct-secret"\nexport DEEPGRAM_API_KEY=dg-old\n', encoding="utf-8"
    )
    read = machine_.detect(VENDORS, {"DEEPGRAM_API_KEY": "dg-secret", "OTHER": "x"}, run=fake, home=tmp_path)
    assert read.cards == (machine_.Card("NVIDIA L4", 22.5), machine_.Card("NVIDIA L4", 22.5))
    assert read.keys_found == {"cartesia": "~/.zshrc", "deepgram": "the environment"}
    assert read.cores >= 1
    assert "dg-secret" not in str(read) and "ct-secret" not in str(read)
    assert machine_.detect(VENDORS, {}, run=lambda _command: None, home=tmp_path).cards == ()


def test_a_key_is_found_in_the_environment_else_in_a_shell_file(tmp_path: Path) -> None:
    """`export NAME=value` and `NAME=value` lines place a key, whatever their value."""
    (tmp_path / ".bashrc").write_text(
        "# keys\nexport ANTHROPIC_API_KEY='sk-ant'\nDEEPGRAM_API_KEY=$(cat ~/dg)\nexport PATH=$PATH:/x\n",
        encoding="utf-8",
    )
    assert machine_.where_is_key("ANTHROPIC_API_KEY", {"ANTHROPIC_API_KEY": "sk-env"}, tmp_path) == "the environment"
    assert machine_.where_is_key("ANTHROPIC_API_KEY", {}, tmp_path) == "~/.bashrc"
    assert machine_.where_is_key("DEEPGRAM_API_KEY", {}, tmp_path) == "~/.bashrc"
    assert machine_.where_is_key("CARTESIA_API_KEY", {}, tmp_path) is None
    # A home with no shell files at all is nowhere, not an error.
    assert machine_.where_is_key("ANTHROPIC_API_KEY", {}, tmp_path / "empty") is None


def test_ollamas_models_are_none_when_nothing_answers_on_its_port() -> None:
    """No Ollama on this machine: an empty list, no error."""
    if not machine_.answers(machine_.OLLAMA_PORT):
        assert machine_.ollama_models() == ()
