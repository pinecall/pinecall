"""The model servers `setup` brings up: what is pulled and by whom, and the loop left free meanwhile."""

import asyncio
import subprocess
import threading
from pathlib import Path

import pytest

from runtime.cli.command import Context
from runtime.cli.output import Printer
from runtime.cli.setup import models
from runtime.cli.setup.choices import LOCAL_EMBEDDER, MODEL_PORTS, Choices
from runtime.config import load_settings
from runtime.exceptions import UpstreamError
from runtime.providers.catalog import Catalog
from runtime.providers.service import machine

ON_KEYS = Choices(stt="deepgram", llm="anthropic", tts="cartesia")


def composed(monkeypatch: pytest.MonkeyPatch) -> list[tuple[list[str], str]]:
    """Every compose verb `models_up` runs, with the thinking model it was given, and Docker never asked."""
    ran: list[tuple[list[str], str]] = []

    def record(
        compose: list[str], profiles: list[str], verb: list[str], environment: dict[str, str], failed: str
    ) -> None:
        ran.append((verb, environment["LOCAL_LLM"]))

    monkeypatch.setattr(models, "_compose", record)
    return ran


def test_a_machine_that_thinks_on_vendors_keys_still_pulls_the_embedders_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No stage is local: Ollama runs for the embedder, and the puller runs once, given no thinking model."""
    ran = composed(monkeypatch)
    served = models.models_up(tmp_path, ON_KEYS, host_ollama=False)
    assert ran == [
        (["up", "-d", "--remove-orphans", "ollama"], ""),
        (["run", "--rm", "ollama-models"], ""),
        (["up", "-d", "--wait", "ollama"], ""),
    ]
    assert served == [f"Ollama :{MODEL_PORTS['Ollama']} ({LOCAL_EMBEDDER})"]


def test_each_open_model_is_pulled_in_a_run_of_its_own(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The thinking's model and a judge's: one run of the puller each, the embedder's model with both."""
    ran = composed(monkeypatch)
    two = Choices(stt="deepgram", llm="local/gemma4:12b", tts="cartesia", judge="local/qwen3:8b")
    models.models_up(tmp_path, two, host_ollama=False)
    assert [given for verb, given in ran if verb[0] == "run"] == ["gemma4:12b", "qwen3:8b"]


def test_ollama_with_no_thinking_model_is_healthy_once_it_answers() -> None:
    """The shipped compose asks the thinking's model only when there is one, and pulls the embedder's whatever."""
    shipped = (Path(models.__file__).parent / "shipped" / "models.yaml").read_text(encoding="utf-8")
    assert "if [ -z '${LOCAL_LLM}' ]; then ollama list >/dev/null; else ollama run" in shipped
    pulled, _, thinking = shipped.partition("ollama pull bge-m3\n")
    assert pulled and 'if [ -n "${LOCAL_LLM}" ]; then\n          ollama pull ${LOCAL_LLM}\n' in thinking


def test_the_puller_reads_nothing_of_the_terminal_setup_was_typed_at(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`ollama run` with no prompt reads one from stdin: the shipped puller gives it none, and compose no terminal."""
    shipped = (Path(models.__file__).parent / "shipped" / "models.yaml").read_text(encoding="utf-8")
    assert 'ollama run ${LOCAL_LLM} "" </dev/null >/dev/null' in shipped
    handed: list[object] = []

    def run(command: list[str], **how: object) -> subprocess.CompletedProcess[str]:
        handed.append(how.get("stdin"))
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", run)
    models.models_up(tmp_path, Choices(stt="deepgram", llm="local/gemma4:12b", tts="cartesia"), host_ollama=False)
    assert handed and all(stdin is subprocess.DEVNULL for stdin in handed)


def pulls_on_host(monkeypatch: pytest.MonkeyPatch, held: tuple[str, ...], *, refused: str = "") -> list[list[str]]:
    """Every command `pull_on_host` hands this machine's Ollama, which holds `held` and refuses with `refused`."""
    ran: list[list[str]] = []

    def run(command: list[str], **_how: object) -> subprocess.CompletedProcess[str]:
        ran.append(command)
        return subprocess.CompletedProcess(command, 1 if refused else 0, "", refused)

    def on_path(_name: str) -> str:
        return "/usr/local/bin/ollama"

    monkeypatch.setattr(machine, "ollama_models", lambda: held)
    monkeypatch.setattr(models, "which", on_path)
    monkeypatch.setattr(subprocess, "run", run)
    return ran


def test_a_model_this_machines_ollama_holds_is_not_asked_of_the_registry_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A held model is left as it is, named bare or by its tag; the one missing is the one pulled."""
    ran = pulls_on_host(monkeypatch, ("bge-m3:latest", "gemma3:1b"))
    models.pull_on_host([LOCAL_EMBEDDER, "gemma3:1b", "gemma4:12b"])
    assert ran == [["ollama", "pull", "gemma4:12b"]]


def test_a_pull_this_machines_ollama_refuses_says_which_model_and_why(monkeypatch: pytest.MonkeyPatch) -> None:
    """An Ollama too old for a model answers 412: setup says whose Ollama, the model, and Ollama's own words."""
    refusal = "Error: pull model manifest: 412: requires a newer version of Ollama"
    pulls_on_host(monkeypatch, (), refused=refusal)
    with pytest.raises(UpstreamError) as said:
        models.pull_on_host(["gemma4:12b"])
    assert "the Ollama this machine runs did not pull gemma4:12b" in str(said.value)
    assert refusal in str(said.value)


async def test_the_loop_stays_free_while_the_models_come_up(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Docker's minutes run on a thread: what the run holds open on the loop, the signal's ear, is still served."""
    loop_ran = threading.Event()

    def minutes_of_docker(where: Path, choices: Choices, *, host_ollama: bool, card: bool) -> list[str]:
        assert loop_ran.wait(timeout=5.0), "the loop was held while the models came up"
        return []

    async def nothing_seeded(runtime: Context, row: Catalog, keys: dict[str, str]) -> None:
        return None

    def no_ollama_of_its_own(_port: int) -> bool:
        return False

    monkeypatch.setattr(models, "models_up", minutes_of_docker)
    monkeypatch.setattr(models, "seed", nothing_seeded)
    monkeypatch.setattr(models, "warm_embedder", lambda: None)
    monkeypatch.setattr(machine, "answers", no_ollama_of_its_own)
    asyncio.get_running_loop().call_soon(loop_ran.set)
    runtime = Context(load_settings(), Printer(as_json=False))
    await models.models(runtime, tmp_path, ON_KEYS, {}, card=False)
