"""What this machine can run: its card, memory and cores read, and the stack that fits them, from what was measured."""

import csv
import json
import os
import platform as host
import re
import socket
import subprocess
import urllib.request
from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from shutil import which
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.enums import Stage
from runtime.exceptions import ValidationError
from runtime.kit.text import a_list, a_mapping
from runtime.platform import service as platform

# The word for an open model on a machine of one's own, in any stage's choice: `local/gemma4:12b`.
LOCAL = "local"
OLLAMA_PORT = 11434
# The margin kept on a card beside what the servers and the model hold.
HEADROOM_GIB = 1.5
# The local model that reads the end of a turn off the audio, where the ears run here.
SMART_TURN = "smart-turn"

# Where a key is looked for after the environment: the shell's own files, in the order a person
# would name them. Only `export NAME=value` and `NAME=value` lines are read, and only the one
# variable asked for; where it is set is said, its value is never read into anything here.
SHELL_FILES = (".zshrc", ".zprofile", ".bashrc", ".bash_profile", ".profile")
THE_ENVIRONMENT = "the environment"
A_SHELL_LINE = re.compile(r"^\s*(?:export\s+)?([A-Z][A-Z0-9_]*)=(.*?)\s*$")
# A value that is itself an expansion (`$OTHER`, `$(…)`) is left to the shell.
EXPANDS = ("$", "`")
NOT_A_MEASURED_ROW = "line {number} of the measured file is not a model, a stage on keys or a server: {line!r}"

# A GPU's memory is the whole budget; a Mac's unified memory is shared with everything else running.
A_MACS_SHARE = 0.75
GIB = 2**30
NVIDIA_SMI = ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"]
type Run = Callable[[list[str]], str | None]


@dataclass(frozen=True, slots=True)
class MeasuredModel:
    """One open model as it was measured: what it holds on a card, how soon it speaks, what it did."""

    model: str
    needs_gib: float
    first_token_s: float
    # What it did when measured, in the words of the test it ran.
    did: str
    note: str


# No vendor and no model is named in code: which open models were measured, which vendors a machine
# with no GPU runs on and what each local server holds on a card are data, written once a measurement
# is made and kept as a setting of the box, the best model first.
@dataclass(frozen=True, slots=True)
class Measured:
    """What was measured, the best model first; the vendor each stage runs on keys; what each local server holds."""

    models: tuple[MeasuredModel, ...]
    on_keys: Mapping[Stage, str]
    servers_gib: Mapping[str, float] = field(default_factory=dict[str, float])

    def __post_init__(self) -> None:
        missing = [stage for stage in Stage if stage not in self.on_keys]
        if missing:
            raise ValidationError(f"what was measured names a vendor for every stage on keys, and not for {missing}")


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


# ── what was measured, as the box keeps it ──


def _load_measured(value: Mapping[str, Any]) -> Measured:
    return Measured(
        models=tuple(MeasuredModel(**one) for one in value.get("models", [])),
        on_keys={Stage(stage): str(vendor) for stage, vendor in value.get("on_keys", {}).items()},
        servers_gib={str(name): float(gib) for name, gib in value.get("servers_gib", {}).items()},
    )


def _dump_measured(measured: Measured) -> dict[str, Any]:
    return {
        "models": [asdict(one) for one in measured.models],
        "on_keys": {stage.value: vendor for stage, vendor in measured.on_keys.items()},
        "servers_gib": dict(measured.servers_gib),
    }


MEASURED: platform.Setting[Measured] = platform.Setting("measured", _load_measured, _dump_measured)


async def find_measured(session: AsyncSession) -> Measured | None:
    """What was measured, as the box was told; None on a box nobody told."""
    return await platform.find_setting(session, MEASURED)


async def put_measured(session: AsyncSession, measured: Measured) -> None:
    """Keep what was measured, replacing what the box held."""
    await platform.put_setting(session, MEASURED, measured)


# ── the machine read ──


def detect(
    vendors: Iterable[str], environ: Mapping[str, str] = os.environ, run: Run | None = None, home: Path | None = None
) -> Machine:
    """This machine, read from the system: no model loaded, nothing written; the vendors' keys placed, never read."""
    ask = run or _run
    cards = _read_cards(ask(NVIDIA_SMI))
    brand = ask(["sysctl", "-n", "machdep.cpu.brand_string"]) if host.system() == "Darwin" else None
    found: dict[str, str] = {}
    for vendor in sorted(set(vendors)):
        where = where_is_key(key_variable(vendor), environ, home)
        if where is not None:
            found[vendor] = where
    return Machine(
        system=host.system().lower(),
        arch=host.machine(),
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
    return next((name for name, _ in shell_lines_of(variable, home)), None)


# Every line of the shell's files that sets the variable, as (file name, value), in file order.
def key_from_shell(variable: str, home: Path | None = None) -> str | None:
    """A variable's value as a shell file sets it, when the line is plain text; None when it is nowhere or expands."""
    for _, value in shell_lines_of(variable, home):
        plain = value.strip()
        if len(plain) >= 2 and plain[0] == plain[-1] and plain[0] in "\"'":
            plain = plain[1:-1]
        if plain and not any(mark in plain for mark in EXPANDS):
            return plain
    return None


# What a machine can run is data, measured once and shipped beside the package (`measured.csv`): a
# model a line, a stage on keys a line, a server a line, `#` lines its notes.
def parse_measured(text: str) -> Measured:
    """What a measured file says: the models in its order, the vendor of each stage on keys, each server's card."""
    models: list[MeasuredModel] = []
    on_keys: dict[Stage, str] = {}
    servers: dict[str, float] = {}
    lines = [line for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    for number, row in enumerate(csv.reader(lines), start=1):
        match row:
            case ["model", model, needs_gib, first_token_s, did, note]:
                models.append(MeasuredModel(model, float(needs_gib), float(first_token_s), did, note))
            case ["keys", stage, vendor]:
                on_keys[Stage(stage)] = vendor
            case ["server", name, gib]:
                servers[name] = float(gib)
            case _:
                raise ValidationError(NOT_A_MEASURED_ROW.format(number=number, line=",".join(row)))
    return Measured(tuple(models), on_keys, servers)


def shell_lines_of(variable: str, home: Path | None = None) -> list[tuple[str, str]]:
    """The lines of the shell's own files that set a variable, each with the file it is in."""
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


def key_variable(vendor: str) -> str:
    """The environment variable a vendor's key is read from: `DEEPGRAM_API_KEY`."""
    return f"{vendor.upper().replace('-', '_')}_API_KEY"


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


def answers(port: int) -> bool:
    """Whether something accepts a connection on that loopback port."""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


# ── the stack that fits ──


def recommend(machine: Machine, measured: Measured) -> Recommendation:
    """The stack for this machine: the best measured model that fits beside the voice, or the vendors' keys."""
    voice = sum(measured.servers_gib.values())
    on_keys = {stage.value: vendor for stage, vendor in measured.on_keys.items()}
    if machine.cards:
        on, budget, taken = "gpu", sum(card.memory_gib for card in machine.cards), voice + HEADROOM_GIB
    elif machine.apple_silicon:
        on, budget, taken = "apple", round(machine.ram_gib * A_MACS_SHARE, 1), HEADROOM_GIB
    else:
        on, budget, taken = "cpu", 0.0, 0.0
    room = max(0.0, budget - taken)
    candidates = tuple(_fit(one, room) for one in measured.models)
    keys: dict[str, dict[str, object]] = {
        stage: {
            "vendor": vendor,
            "variable": key_variable(vendor),
            "found": vendor in machine.keys_found,
            "where": machine.keys_found.get(vendor),
        }
        for stage, vendor in on_keys.items()
    }
    fitting = next((one for one in candidates if one.fits), None)
    notes: list[str] = []
    if on == "cpu":
        notes.append("no GPU: the measured local models need one; the vendors' keys run every stage")
        stack = on_keys | {"turn": Stage.stt.value}
    elif fitting is None:
        notes.append(f"{budget:.0f} GB is short of every measured model beside the voice: the thinking on a key")
        stack = {"stt": LOCAL, "turn": SMART_TURN, "llm": on_keys[Stage.llm.value], "tts": LOCAL}
    else:
        stack = {"stt": LOCAL, "turn": SMART_TURN, "llm": f"{LOCAL}/{fitting.model}", "tts": LOCAL}
    if on == "apple":
        notes.append("a Mac thinks on its own Ollama (Metal); the ears and the voice run in CPU containers, unmeasured")
    if not machine.docker:
        notes.append("Docker is not installed: the local servers and LiveKit need it")
    stack = stack | {"judge": stack["llm"], "caller": stack["llm"]}
    return Recommendation(on, round(budget, 1), round(room, 1), stack, candidates, keys, tuple(notes))


# Reads the hardware with a subprocess, two sockets and the shell's files: run in a thread by whoever
# is on an event loop.
def recommendation(measured: Measured, environ: Mapping[str, str] = os.environ) -> dict[str, Any]:
    """What `setup --recommend` prints: the machine and the stack for it."""
    machine = detect(measured.on_keys.values(), environ)
    return {"machine": asdict(machine), "recommendation": asdict(recommend(machine, measured))}


# ── private ──


def _fit(one: MeasuredModel, room: float) -> Candidate:
    return Candidate(
        model=one.model,
        needs_gib=one.needs_gib,
        fits=one.needs_gib <= room,
        short_by_gib=round(max(0.0, one.needs_gib - room), 1),
        first_token_s=one.first_token_s,
        did=one.did,
        note=one.note,
    )


def _read_cards(listed: str | None) -> tuple[Card, ...]:
    cards: list[Card] = []
    for line in (listed or "").splitlines():
        name, _, memory = line.rpartition(",")
        try:
            cards.append(Card(name.strip(), round(float(memory.strip()) / 1024, 1)))
        except ValueError:
            continue
    return tuple(cards)


def _ram_bytes(ask: Run) -> int:
    if host.system() == "Darwin":
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
