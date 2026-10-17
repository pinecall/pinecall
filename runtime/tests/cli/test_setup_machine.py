"""What `setup --recommend` says: the machine as read, and the stack that fits it from what was measured."""

import dataclasses

from pinecall_runtime.cli import setup_machine as machine_

THE_30B = "qwen3:30b-a3b-instruct-2507-q4_K_M"


A_LINUX_BOX = machine_.Machine(
    system="linux",
    arch="x86_64",
    cores=8,
    ram_gib=32.0,
    cards=(),
    apple_silicon=False,
    docker=True,
    ollama_here=False,
    keys_found=(),
)


def a_machine(**given: object) -> machine_.Machine:
    return dataclasses.replace(A_LINUX_BOX, **given)


def test_a_24_gb_card_runs_the_12b_beside_the_voice_and_a_40_gb_one_the_30b() -> None:
    """The budget is the card's memory less the ears, the voice, the embedder and a margin; the best that fits wins."""
    l4 = machine_.recommend(a_machine(cards=(machine_.Card("NVIDIA L4", 23.0),)))
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
    a100 = machine_.recommend(a_machine(cards=(machine_.Card("NVIDIA A100-SXM4-40GB", 40.0),)))
    assert a100.stack["llm"] == f"local/{THE_30B}" and a100.stack["judge"] == f"local/{THE_30B}"


def test_no_card_means_the_vendors_keys_and_says_which_are_set() -> None:
    """A machine with no GPU is told the measured models need one; its stack is the three vendors, keys found marked."""
    cpu = machine_.recommend(a_machine(keys_found=("deepgram",)))
    assert cpu.on == "cpu" and cpu.budget_gib == 0
    assert cpu.stack == {
        "stt": "deepgram",
        "llm": "anthropic",
        "tts": "cartesia",
        "turn": "stt",
        "judge": "anthropic",
        "caller": "anthropic",
    }
    assert cpu.keys["stt"] == {"vendor": "deepgram", "variable": "DEEPGRAM_API_KEY", "found": True}
    assert cpu.keys["llm"]["found"] is False
    assert any("no GPU" in note for note in cpu.notes)
    assert all(not one.fits for one in cpu.candidates)


def test_a_mac_counts_three_quarters_of_its_memory_and_runs_the_voice_on_its_cpu() -> None:
    """Apple silicon: Ollama on Metal gets most of the unified memory; the containers' CPU images are unmeasured."""
    mac = machine_.recommend(a_machine(system="darwin", arch="arm64", ram_gib=32.0, apple_silicon=True))
    assert mac.on == "apple" and mac.budget_gib == 24.0
    assert mac.stack["llm"] == f"local/{THE_30B}"
    assert any("unmeasured" in note for note in mac.notes)
    assert machine_.recommend(a_machine(system="darwin", arch="arm64", ram_gib=24.0, apple_silicon=True)).stack[
        "llm"
    ] == ("local/gemma4:12b")
    small = machine_.recommend(a_machine(system="darwin", arch="arm64", ram_gib=8.0, apple_silicon=True))
    assert small.stack["llm"] == "anthropic" and small.stack["stt"] == "local"


def test_the_machine_is_read_off_nvidia_smi_and_the_environment() -> None:
    """Cards parsed from nvidia-smi's CSV; the key variables set are listed by vendor, their values never kept."""

    def fake(command: list[str]) -> str | None:
        if command[0] == "nvidia-smi":
            return "NVIDIA L4, 23034\nNVIDIA L4, 23034\n"
        return None

    read = machine_.detect({"DEEPGRAM_API_KEY": "dg-secret", "OTHER": "x"}, run=fake)
    assert read.cards == (machine_.Card("NVIDIA L4", 22.5), machine_.Card("NVIDIA L4", 22.5))
    assert read.keys_found == ("deepgram",)
    assert read.cores >= 1
    assert "dg-secret" not in str(read)
    assert machine_.detect({}, run=lambda _command: None).cards == ()
