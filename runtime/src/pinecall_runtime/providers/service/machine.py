"""What this machine can run: its card, memory and cores read, and the stack that fits them, from what was measured."""

import json
import os
import platform
import re
import socket
import subprocess
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from shutil import which
from typing import Any

from pinecall_runtime.kit.text import a_list, a_mapping

# The word for an open model on a machine of one's own, in any stage's choice: `local/gemma4:12b`.
LOCAL = "local"
OLLAMA_PORT = 11434

# What each server holds on a card, measured on an NVIDIA L4 (2026-10-17), and the margin kept.
VOICE_GIB = {"whisper": 2.3, "kokoro": 1.1, "embedder": 0.9}
HEADROOM_GIB = 1.5
# What was measured, the best first. The 30B on an A100 (2026-10-18) against the real voice turns
# of the clinic's agent: the tool called, the written goldens, the spoken ones. The two Gemmas on
# an L4 (2026-10-17) with front-desk's prompt, three turns three times each: a message left, a
# question the documents answer, small talk.
MEASURED: tuple[dict[str, Any], ...] = (
    {
        "model": "nemotron-3.5-lightning:30b-a3b",
        "needs_gib": 25.0,
        "first_token_s": 0.45,
        "did": "tool called 18/18 on voice turns · written goldens 5/5 · spoken 2/3",
        "note": "30B of knowledge, 3B active per token: the fastest that did everything; whole on a card only with "
        "40 GB beside the voice",
    },
    {
        "model": "gemma4:12b",
        "needs_gib": 9.0,
        "first_token_s": 0.9,
        "did": "message 3/3 · documents 3/3 · talk 3/3",
        "note": "did everything on 24 GB; reads the whole prompt every turn (no prefix cache), so 1.3-1.7 s to the "
        "first token on a call",
    },
    {
        "model": "gemma4:e4b",
        "needs_gib": 7.5,
        "first_token_s": 0.8,
        "did": "message 2/3 · documents 3/3 · talk 3/3",
        "note": "the model the Pipecat local stack ships; missed the message once in three",
    },
)
# Not recommended, and why: qwen3:30b-a3b-2507 called the tool 1/18 on the real voice turns (it
# says "Let me check…" and stops); qwen3.8:27b called it 18/18 but took 1.5-2.8 s to its first
# token; qwen3:8b and 14b never called it; qwen3:4b thought aloud with thinking off; llama3.1:8b,
# llama3.2:3b and gpt-oss:20b called it on a greeting; gemma4:26b took 3 s to its first token,
# part of it on the CPU.
# The vendors a machine with no GPU runs on, a stage each.
ON_KEYS = {"stt": "deepgram", "llm": "anthropic", "tts": "cartesia"}

# Where a key is looked for after the environment: the shell's own files, in the order a person
# would name them. Only `export NAME=value` and `NAME=value` lines are read, and only the one
# variable asked for; a value that is itself an expansion (`$OTHER`, `$(…)`) is left to the shell.
SHELL_FILES = (".zshrc", ".zprofile", ".bashrc", ".bash_profile", ".profile")
THE_ENVIRONMENT = "the environment"
A_SHELL_LINE = re.compile(r"^\s*(?:export\s+)?([A-Z][A-Z0-9_]*)=(.*?)\s*$")
EXPANDS = ("$", "`")

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
    # The models the Ollama here holds already, by tag; none when no Ollama answers.
    ollama_models: tuple[str, ...]
    # Where each vendor's key variable was found, by vendor: the environment or a shell file's name;
    # a vendor whose key is nowhere is not listed. The values are never read into this.
    keys_found: dict[str, str]


@dataclass(frozen=True)
class Candidate:
    """A measured model and whether it fits this machine."""

    model: str
    needs_gib: float
    fits: bool
    short_by_gib: float
    first_token_s: float
    # What it did when measured, in the words of the test it ran.
    did: str
    note: str


@dataclass(frozen=True)
class Recommendation:
    """The stack this machine should run, and why."""

    on: str
    budget_gib: float
    # What the budget leaves for the thinking's model, beside the voice and the margin.
    room_gib: float
    stack: dict[str, str]
    candidates: tuple[Candidate, ...]
    keys: dict[str, dict[str, object]]
    notes: tuple[str, ...]


def detect(environ: Mapping[str, str] = os.environ, run: Run | None = None, home: Path | None = None) -> Machine:
    """This machine, read from the system: no model loaded, nothing written."""
    ask = run or _run
    cards = _cards(ask(NVIDIA_SMI))
    brand = ask(["sysctl", "-n", "machdep.cpu.brand_string"]) if platform.system() == "Darwin" else None
    found: dict[str, str] = {}
    for vendor in sorted(ON_KEYS.values()):
        where = where_is_key(key_variable(vendor), environ, home)
        if where is not None:
            found[vendor] = where
    return Machine(
        system=platform.system().lower(),
        arch=platform.machine(),
        cores=os.cpu_count() or 1,
        ram_gib=round(_ram_bytes(ask) / GIB, 1),
        cards=cards,
        apple_silicon=brand is not None and "Apple" in brand,
        docker=which("docker") is not None,
        ollama_here=answers(OLLAMA_PORT) or which("ollama") is not None,
        ollama_models=ollama_models(),
        keys_found=found,
    )


def where_is_key(variable: str, environ: Mapping[str, str] = os.environ, home: Path | None = None) -> str | None:
    """Where a variable is set: `the environment`, else the shell file holding it, else None; its value is not read."""
    if environ.get(variable, "").strip():
        return THE_ENVIRONMENT
    return next((name for name, _ in _shell_lines(variable, home)), None)


def key_from_shell(variable: str, home: Path | None = None) -> str | None:
    """A variable's value as a shell file sets it, when the line is plain text; None when it is nowhere or expands."""
    for _, value in _shell_lines(variable, home):
        plain = value.strip()
        if len(plain) >= 2 and plain[0] == plain[-1] and plain[0] in "\"'":
            plain = plain[1:-1]
        if plain and not any(mark in plain for mark in EXPANDS):
            return plain
    return None


def ollama_models() -> tuple[str, ...]:
    """The tags the Ollama on this machine holds, from its own list; none when nothing answers."""
    if not answers(OLLAMA_PORT):
        return ()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{OLLAMA_PORT}/api/tags", timeout=3) as answer:
            listed: object = json.load(answer)
    except (OSError, ValueError):
        return ()
    models = listed.get("models") if a_mapping(listed) else None
    if not a_list(models):
        return ()
    names = [one.get("name") for one in models if a_mapping(one)]
    return tuple(sorted(name for name in names if isinstance(name, str)))


def recommend(machine: Machine) -> Recommendation:
    """The stack for this machine: the best measured model that fits beside the voice, or the vendors' keys."""
    voice = sum(VOICE_GIB.values())
    headroom = HEADROOM_GIB
    if machine.cards:
        on, budget, taken = "gpu", sum(card.memory_gib for card in machine.cards), voice + headroom
    elif machine.apple_silicon:
        on, budget, taken = "apple", round(machine.ram_gib * A_MACS_SHARE, 1), headroom
    else:
        on, budget, taken = "cpu", 0.0, 0.0
    room = max(0.0, budget - taken)
    candidates = tuple(_candidate(one, room) for one in MEASURED)
    keys: dict[str, dict[str, object]] = {}
    for stage, vendor in ON_KEYS.items():
        keys[str(stage)] = {
            "vendor": str(vendor),
            "variable": key_variable(str(vendor)),
            "found": vendor in machine.keys_found,
            "where": machine.keys_found.get(vendor),
        }
    fitting = next((one for one in candidates if one.fits), None)
    notes: list[str] = []
    if on == "cpu":
        notes.append("no GPU: the measured local models need one; the vendors' keys run every stage")
        stack = {stage: str(vendor) for stage, vendor in ON_KEYS.items()} | {"turn": "stt"}
    elif fitting is None:
        notes.append(f"{budget:.0f} GB is short of every measured model beside the voice: the thinking on a key")
        stack = {"stt": LOCAL, "turn": "smart-turn", "llm": ON_KEYS["llm"], "tts": LOCAL}
    else:
        stack = {"stt": LOCAL, "turn": "smart-turn", "llm": f"{LOCAL}/{fitting.model}", "tts": LOCAL}
    if on == "apple":
        notes.append("a Mac thinks on its own Ollama (Metal); the ears and the voice run in CPU containers, unmeasured")
    if not machine.docker:
        notes.append("Docker is not installed: the local servers and LiveKit need it")
    stack = stack | {"judge": stack["llm"], "caller": stack["llm"]}
    return Recommendation(on, round(budget, 1), round(room, 1), stack, candidates, keys, tuple(notes))


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
        did=str(one["did"]),
        note=str(one["note"]),
    )


# Every line of the shell's files that sets the variable, as (file name, value), in file order.
def _shell_lines(variable: str, home: Path | None) -> list[tuple[str, str]]:
    lines: list[tuple[str, str]] = []
    for name in SHELL_FILES:
        try:
            text = ((home or Path.home()) / name).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for line in text.splitlines():
            matched = A_SHELL_LINE.match(line)
            if matched and matched.group(1) == variable:
                lines.append((f"~/{name}", matched.group(2)))
    return lines


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


def key_variable(vendor: str) -> str:
    """The environment variable a vendor's key is read from: `DEEPGRAM_API_KEY`."""
    return f"{vendor.upper().replace('-', '_')}_API_KEY"


def answers(port: int) -> bool:
    """Whether something accepts a connection on that loopback port."""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False
