"""What this machine can run: its card, memory and cores read, and the stack that fits them, from what was measured."""

import json
import os
import platform
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from importlib.resources import files
from shutil import which
from typing import Any

from pinecall_runtime.cli.setup_models import LOCAL, MODEL_PORTS, key_variable
from pinecall_runtime.cli.setup_servers import answers

# A GPU's memory is the whole budget; a Mac's unified memory is shared with everything else running.
A_MACS_SHARE = 0.75
GIB = 2**30
NVIDIA_SMI = ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"]
type Run = Callable[[list[str]], str | None]


@dataclass(frozen=True)
class Card:
    """One GPU and its memory."""

    name: str
    memory_gib: float


@dataclass(frozen=True)
class Machine:
    """What was read off this machine."""

    system: str
    arch: str
    cores: int
    ram_gib: float
    cards: tuple[Card, ...]
    apple_silicon: bool
    docker: bool
    ollama_here: bool
    # The key variables set in the environment, by vendor; the values are never read into this.
    keys_found: tuple[str, ...]


@dataclass(frozen=True)
class Candidate:
    """A measured model and whether it fits this machine."""

    model: str
    needs_gib: float
    fits: bool
    short_by_gib: float
    first_token_s: float
    message: str
    documents: str
    talk: str
    note: str


@dataclass(frozen=True)
class Recommendation:
    """The stack this machine should run, and why."""

    on: str
    budget_gib: float
    stack: dict[str, str]
    candidates: tuple[Candidate, ...]
    keys: dict[str, dict[str, object]]
    notes: tuple[str, ...]


def detect(environ: Mapping[str, str] = os.environ, run: Run | None = None) -> Machine:
    """This machine, read from the system: no model loaded, nothing written."""
    ask = run or _run
    cards = _cards(ask(NVIDIA_SMI))
    brand = ask(["sysctl", "-n", "machdep.cpu.brand_string"]) if platform.system() == "Darwin" else None
    vendors = sorted(vendor for vendor in _measured()["keys"].values() if environ.get(key_variable(vendor), "").strip())
    return Machine(
        system=platform.system().lower(),
        arch=platform.machine(),
        cores=os.cpu_count() or 1,
        ram_gib=round(_ram_bytes(ask) / GIB, 1),
        cards=cards,
        apple_silicon=brand is not None and "Apple" in brand,
        docker=which("docker") is not None,
        ollama_here=answers(MODEL_PORTS["Ollama"]) or which("ollama") is not None,
        keys_found=tuple(vendors),
    )


def recommend(machine: Machine) -> Recommendation:
    """The stack for this machine: the best measured model that fits beside the voice, or the vendors' keys."""
    measured = _measured()
    voice = sum(float(gib) for gib in measured["voice_gib"].values())
    headroom = float(measured["headroom_gib"])
    if machine.cards:
        on, budget, taken = "gpu", sum(card.memory_gib for card in machine.cards), voice + headroom
    elif machine.apple_silicon:
        on, budget, taken = "apple", round(machine.ram_gib * A_MACS_SHARE, 1), headroom
    else:
        on, budget, taken = "cpu", 0.0, 0.0
    candidates = tuple(_candidate(one, budget - taken) for one in measured["llms"])
    keys: dict[str, dict[str, object]] = {}
    for stage, vendor in measured["keys"].items():
        keys[str(stage)] = {
            "vendor": str(vendor),
            "variable": key_variable(str(vendor)),
            "found": vendor in machine.keys_found,
        }
    fitting = next((one for one in candidates if one.fits), None)
    notes: list[str] = []
    if on == "cpu":
        notes.append("no GPU: the measured local models need one; the vendors' keys run every stage")
        stack = {stage: str(vendor) for stage, vendor in measured["keys"].items()} | {"turn": "stt"}
    elif fitting is None:
        notes.append(f"{budget:.0f} GB is short of every measured model beside the voice: the thinking on a key")
        stack = {"stt": LOCAL, "turn": "smart-turn", "llm": str(measured["keys"]["llm"]), "tts": LOCAL}
    else:
        stack = {"stt": LOCAL, "turn": "smart-turn", "llm": f"{LOCAL}/{fitting.model}", "tts": LOCAL}
    if on == "apple":
        notes.append("a Mac thinks on its own Ollama (Metal); the ears and the voice run in CPU containers, unmeasured")
    if not machine.docker:
        notes.append("Docker is not installed: the local servers and LiveKit need it")
    stack = stack | {"judge": stack["llm"], "caller": stack["llm"]}
    return Recommendation(on, round(budget, 1), stack, candidates, keys, tuple(notes))


def recommendation(environ: Mapping[str, str] = os.environ) -> dict[str, Any]:
    """What `setup --recommend` prints: the machine and the stack for it."""
    machine = detect(environ)
    return {"machine": asdict(machine), "recommendation": asdict(recommend(machine))}


# ── private ──


def _candidate(one: Mapping[str, Any], room: float) -> Candidate:
    needs = float(one["needs_gib"])
    return Candidate(
        model=str(one["model"]),
        needs_gib=needs,
        fits=needs <= room,
        short_by_gib=round(max(0.0, needs - room), 1),
        first_token_s=float(one["first_token_s"]),
        message=str(one["message"]),
        documents=str(one["documents"]),
        talk=str(one["talk"]),
        note=str(one["note"]),
    )


def _cards(listed: str | None) -> tuple[Card, ...]:
    cards: list[Card] = []
    for line in (listed or "").splitlines():
        name, _, memory = line.rpartition(",")
        try:
            cards.append(Card(name.strip(), round(float(memory.strip()) / 1024, 1)))
        except ValueError:
            continue
    return tuple(cards)


def _ram_bytes(ask: Run) -> int:
    if platform.system() == "Darwin":
        said = ask(["sysctl", "-n", "hw.memsize"])
        return int(said.strip()) if said and said.strip().isdigit() else 0
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (ValueError, OSError, AttributeError):
        return 0


def _run(command: list[str]) -> str | None:
    if which(command[0]) is None:
        return None
    try:
        ran = subprocess.run(command, capture_output=True, text=True, check=False, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return ran.stdout if ran.returncode == 0 else None


def _measured() -> dict[str, Any]:
    text = files("pinecall_runtime.cli").joinpath("local", "measured.json").read_text(encoding="utf-8")
    loaded: dict[str, Any] = json.loads(text)
    return loaded
