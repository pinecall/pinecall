"""Pinecall's judges and personas, in judging/library/, read once; and what a class may name of them."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Literal

from runtime.enums import JudgeAnswer, JudgeRunsWhen
from runtime.exceptions import ValidationError
from runtime.judging.service.specs import READS, Behavior, JudgeSpec, Persona

NONE_OF_PINECALLS = "{name} is none of Pinecall's {kind}: `pinecall {kind} list` names them"
ONE_OF_PINECALLS = (
    "{name} is one of Pinecall's {kind}: switch it on in the class's `{kind}`, or write your own under another name"
)
TWICE = "the class declares two {kind} called {name}"

JUDGES = Path(__file__).parent.parent / "library" / "judges"
PERSONAS = Path(__file__).parent.parent / "library" / "personas"

# A library persona's body: its goal, then this line, then one expectation a line, each "- …".
EXPECTS = "Expects:"

# What decides, before any model is asked, that a judge does not apply: an irreversible tool
# never ran, the call came in, the simulated caller expected nothing. Code reads facts here; it
# never answers the question.
type Gate = Literal["none", "irreversible-tools", "outbound", "expectations"]
GATES: tuple[Gate, ...] = ("none", "irreversible-tools", "outbound", "expectations")

NOT_A_PAGE = "{path}: a judge of the library opens with its front matter between two --- lines"
NOT_A_FIELD = "{path}: {field} is {value!r}, not one of {allowed}"


@dataclass(frozen=True, slots=True)
class Written:
    """One of Pinecall's judges: its spec, what it holds a call to, its version and default."""

    spec: JudgeSpec
    summary: str
    version: int
    on_by_default: bool
    gate: Gate
    # What it saves an org from, in a line, and whether Pinecall says to switch it on first.
    why: str = ""
    recommended: bool = False


@dataclass(frozen=True, slots=True)
class WrittenPersona:
    """One of Pinecall's personas: the caller, what it is for, its version and default."""

    persona: Persona
    summary: str
    version: int
    on_by_default: bool


# Read once a process: the files ship in the wheel and change only with a release.
@cache
def library_judges() -> dict[str, Written]:
    """Every judge of the library, by name."""
    read = [read_judge(path) for path in sorted(JUDGES.glob("*.md"))]
    return {judge.spec.name: judge for judge in read}


@cache
def library_personas() -> dict[str, WrittenPersona]:
    """Every persona of the library, by name."""
    read = [read_persona(path) for path in sorted(PERSONAS.glob("*.md"))]
    return {written.persona.name: written for written in read}


# A class says "none but Pinecall's" with an empty list: a switch it leaves out is off.
def switches_of_class(on: Sequence[str], library: Mapping[str, object], kind: str) -> dict[str, bool]:
    """The library's switches as a class declares them: the names on, every other off; a stranger refused."""
    for name in on:
        if name not in library:
            raise ValidationError(NONE_OF_PINECALLS.format(name=name, kind=kind))
    return {name: name in on for name in library}


def check_own_names(names: Sequence[str], library: Mapping[str, object], kind: str) -> None:
    """Refuse a name of the class's own that is the library's, or declared twice."""
    for name in names:
        if name in library:
            raise ValidationError(ONE_OF_PINECALLS.format(name=name, kind=kind))
        if names.count(name) > 1:
            raise ValidationError(TWICE.format(name=name, kind=kind))


# The front matter is `key: value` lines; `reads` and `choices` are comma lists. A page says when its
# judge runs under `on`, the word it was written with.
def read_judge(path: Path) -> Written:
    """One page of the library read into its judge; a field it does not know the value of is refused."""
    fields, body = _page(path)
    reads = _list_items(fields.get("reads", ""))
    spec = JudgeSpec(
        name=fields["name"],
        question=body.strip(),
        answer=JudgeAnswer(_one_of(path, "answer", fields.get("answer", "verdict"), tuple(JudgeAnswer))),
        choices=tuple(_list_items(fields.get("choices", ""))),
        when=JudgeRunsWhen(_one_of(path, "on", fields.get("on", "always"), tuple(JudgeRunsWhen))),
        trigger=fields.get("trigger", ""),
        reads=frozenset(read for read in READS if read in reads),
    )
    return Written(
        spec=spec,
        summary=fields.get("summary", ""),
        version=int(fields.get("version", "1")),
        on_by_default=fields.get("default", "off") == "on",
        gate=_one_of(path, "gate", fields.get("gate", "none"), GATES),
        why=fields.get("why", ""),
        recommended=_one_of(path, "recommended", fields.get("recommended", "no"), ("yes", "no")) == "yes",
    )


def read_persona(path: Path) -> WrittenPersona:
    """One page of the library read into its persona: its goal, what it expects, how it acts on the line."""
    fields, body = _page(path)
    goal, _, expected = body.partition(EXPECTS)
    persona = Persona(
        name=fields["name"],
        goal=goal.strip(),
        style=fields.get("style", ""),
        expects=tuple(line.strip().removeprefix("- ").strip() for line in expected.splitlines() if line.strip()),
        tags=tuple(_list_items(fields.get("tags", ""))),
        behavior=_behavior_of(fields),
    )
    return WrittenPersona(
        persona=persona,
        summary=fields.get("summary", ""),
        version=int(fields.get("version", "1")),
        on_by_default=fields.get("default", "off") == "on",
    )


# How the caller acts on a spoken line: `interrupts`, `pause_s`, `interferer_db`, `packet_loss`,
# `backchannels`, `speed` and `ambience` in the front matter; a field left out is a quiet caller's.
def _behavior_of(fields: Mapping[str, str]) -> Behavior:
    noise = fields.get("interferer_db")
    return Behavior(
        interrupts=float(fields.get("interrupts", "0")),
        pause_s=float(fields.get("pause_s", "0")),
        interferer_db=None if noise is None else float(noise),
        packet_loss=float(fields.get("packet_loss", "0")),
        backchannels=float(fields.get("backchannels", "0")),
        speed=float(fields.get("speed", "1")),
        ambience=fields.get("ambience", "television"),
    )


def _one_of[T: str](path: Path, field: str, value: str, allowed: tuple[T, ...]) -> T:
    for each in allowed:
        if value == each:
            return each
    raise ValidationError(NOT_A_FIELD.format(path=path.name, field=field, value=value, allowed=allowed))


def _list_items(text: str) -> list[str]:
    return [item.strip() for item in text.split(",") if item.strip()]


def _page(path: Path) -> tuple[dict[str, str], str]:
    text = path.read_text(encoding="utf-8")
    _, separator, rest = text.partition("---\n")
    head, closing, body = rest.partition("\n---\n")
    if not separator or not closing:
        raise ValidationError(NOT_A_PAGE.format(path=path.name))
    pairs = (line.partition(":") for line in head.splitlines())
    return {key.strip(): value.strip() for key, _, value in pairs}, body.strip()
