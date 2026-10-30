"""Pinecall's judges and personas, in judging/library/, and the panel a finished call meets."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from functools import cache
from pathlib import Path
from typing import Literal

from pinecall_runtime.enums import Direction, JudgeAnswer, JudgeRunsWhen
from pinecall_runtime.exceptions import ValidationError
from pinecall_runtime.judging.service.case import Case
from pinecall_runtime.judging.service.specs import Behavior, JudgeSpec, Persona

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


@dataclass(frozen=True, slots=True)
class Seated:
    """A judge on one call's panel: its spec, what may settle it as N/A first, and whose it is."""

    spec: JudgeSpec
    gate: Gate = "none"
    # The library's version, so a changed question reads as a changed judge; None for the org's own.
    version: int | None = None


@dataclass(frozen=True, slots=True)
class Surroundings:
    """What the seal knows of a call beyond its log, as the judges that read facts are told it."""

    org: str
    # The sentence outbound calls open with; None when the org and the platform set none.
    disclosure: str | None = None
    # A do-not-call fact was written with this call's id (call.opt_out).
    opted_out: bool = False


# Read once a process: the files ship in the wheel and change only with a release.
@cache
def library_judges() -> dict[str, Written]:
    """Every judge of the library, by name."""
    read = [_written(path) for path in sorted(JUDGES.glob("*.md"))]
    return {judge.spec.name: judge for judge in read}


@cache
def library_personas() -> dict[str, WrittenPersona]:
    """Every persona of the library, by name."""
    read = [_written_persona(path) for path in sorted(PERSONAS.glob("*.md"))]
    return {written.persona.name: written for written in read}


def panel_of(case: Case, switches: Mapping[str, bool], own: Sequence[JudgeSpec]) -> list[Seated]:
    """The library's judges switched on, then the org's and the agent's own, for this call."""
    seated = [
        Seated(judge.spec, judge.gate, judge.version)
        for name, judge in library_judges().items()
        if switches.get(name, judge.on_by_default)
    ]
    seated += [Seated(spec) for spec in own]
    return [judge for judge in seated if case.simulated or judge.spec.on is not JudgeRunsWhen.simulations]


def gated(judge: Seated, case: Case) -> str | None:
    """Why the judge does not apply to this call, said before any model is asked; None if it may."""
    match judge.gate:
        case "irreversible-tools" if not _irreversible_ran(case):
            return "no tool this agent declares irreversible ran on this call"
        case "outbound" if case.direction is not Direction.outbound:
            return "the call came in: only an outbound call names who it calls for"
        case "expectations" if not case.expects:
            return "the simulated caller expected nothing of the agent"
        case _:
            return None


def facts_of(case: Case, around: Surroundings) -> str:
    """The facts a judge that reads them is told, one line each."""
    direction = "unknown" if case.direction is None else case.direction.value
    lines = [f"- organisation: {around.org}", f"- direction: {direction}"]
    irreversible = sorted(name for name, effect in _declared_tools(case).items() if effect == "irreversible")
    lines.append(f"- irreversible tools: {', '.join(irreversible) or 'none'}")
    lines += [
        f"- #{line.seq} {line.kind} {line.tool}" + (f" ({line.audience})" if line.audience else "")
        for line in case.gate
        if line.kind != "tool.call"
    ]
    lines.append(f"- an opt-out was written on this call: {'yes' if around.opted_out else 'no'}")
    if around.disclosure:
        lines.append(f'- the disclosure sentence outbound calls open with: "{around.disclosure}"')
    summary = case.summary or {}
    if summary.get("end_reason"):
        lines.append(f"- the call ended: {summary.get('end_reason')}, by {summary.get('ended_by')}")
    if case.expects:
        lines += ["- the simulated caller expected:"]
        lines += [f"  - {line}" for line in case.expects]
    return "\n".join(lines)


# A class says "none but Pinecall's" with an empty list: a switch it leaves out is off.
def declared_switches(on: Sequence[str], library: Mapping[str, object], kind: str) -> dict[str, bool]:
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


def played_on(written: WrittenPersona, llm: str | None, tts: str | None, voice: str | None) -> WrittenPersona:
    """A library persona as the org plays it: its own model and voice, where it chose them."""
    return replace(written, persona=replace(written.persona, llm=llm, tts=tts, voice=voice))


def _irreversible_ran(case: Case) -> bool:
    return any(line.kind == "tool.call" and line.side_effect == "irreversible" for line in case.gate)


def _declared_tools(case: Case) -> dict[str, str]:
    if case.declared is None:
        return {}
    return {name: spec.side_effect for name, spec in case.declared.tools_by_name.items()}


# The front matter is `key: value` lines; `reads` and `choices` are comma lists.
def _written(path: Path) -> Written:
    fields, body = _page(path)
    reads = _listed(fields.get("reads", ""))
    spec = JudgeSpec(
        name=fields["name"],
        question=body.strip(),
        answer=JudgeAnswer(_one_of(path, "answer", fields.get("answer", "verdict"), tuple(JudgeAnswer))),
        choices=tuple(_listed(fields.get("choices", ""))),
        on=JudgeRunsWhen(_one_of(path, "on", fields.get("on", "always"), tuple(JudgeRunsWhen))),
        trigger=fields.get("trigger", ""),
        reads_prompt="prompt" in reads,
        reads_evidence="evidence" in reads,
        reads_facts="facts" in reads,
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


def _written_persona(path: Path) -> WrittenPersona:
    fields, body = _page(path)
    goal, _, expected = body.partition(EXPECTS)
    persona = Persona(
        name=fields["name"],
        goal=goal.strip(),
        style=fields.get("style", ""),
        expects=tuple(line.strip().removeprefix("- ").strip() for line in expected.splitlines() if line.strip()),
        tags=tuple(_listed(fields.get("tags", ""))),
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


def _listed(text: str) -> list[str]:
    return [item.strip() for item in text.split(",") if item.strip()]


def _page(path: Path) -> tuple[dict[str, str], str]:
    text = path.read_text(encoding="utf-8")
    _, separator, rest = text.partition("---\n")
    head, closing, body = rest.partition("\n---\n")
    if not separator or not closing:
        raise ValidationError(NOT_A_PAGE.format(path=path.name))
    pairs = (line.partition(":") for line in head.splitlines())
    return {key.strip(): value.strip() for key, _, value in pairs}, body.strip()
