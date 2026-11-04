"""The judges and the personas a class owns: `own_judge`, `own_persona`, `judges`, `personas`."""

import re
from collections.abc import Mapping, Sequence
from typing import cast

from pydantic import ValidationError

from pinecall.errors import DeclarationRefused
from pinecall.wire.judging import (
    JudgeAnswer,
    JudgeDeclaration,
    JudgeRead,
    JudgeRunsWhen,
    PersonaDeclaration,
)

# The name a judge or a persona is called by: lower-case words joined by hyphens.
A_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

ANSWERS = ("verdict", "choice", "score")
WHENS = ("always", "simulations", "trigger")
READS = ("prompt", "evidence", "facts")
# Fewer than two is not a choice.
FEWEST_CHOICES = 2

NO_QUESTION = "a judge asks a question of a call: write it as asks"
NO_CHOICES = "a judge that answers one of several needs at least two choices"
CHOICES_ONLY = "only a judge that answers one of several takes choices"
NO_TRIGGER = "a judge that runs on a trigger needs the trigger's question"
NOT_A_JUDGE_NAME = (
    '"{name}" is not a judge\'s name: lower-case words joined by hyphens, like offers-next-slot'
)
NO_GOAL = "a persona wants something: write its goal, in the first person"
NO_STYLE = "a persona talks some way: write its style"
NOT_A_PERSONA_NAME = (
    '"{name}" is not a persona\'s name: lower-case words joined by hyphens, like price-shopper'
)
NOT_ONE_OF = '{field} is "{value}", not one of {allowed}'
TWICE = "two {what}s called {name}: a name is declared once"
NOT_DECLARED_SO = (
    "judges and personas are declared with judges(on=[…], own=[…]) and personas(on=[…], own=[…])"
)


def own_judge(  # noqa: PLR0913 - one keyword for each thing a judge is
    *,
    name: str,
    asks: str,
    answer: JudgeAnswer = "verdict",
    choices: Sequence[str] = (),
    when: JudgeRunsWhen = "always",
    trigger: str = "",
    reads: Sequence[JudgeRead] = (),
) -> dict[str, object]:
    """A judge of the agent's own, refused by sentence when wrong; `own=[…]` of `judges` takes it.

    Args:
        name: Lower-case words joined by hyphens: `offers-next-slot`.
        asks: The one sentence the judge model answers about the finished call.
        answer: `verdict` (held or broken), `score` (1 to 5), or `choice` (one of `choices`).
        choices: Two at least, and only for `choice`.
        when: `always`, `simulations`, or `trigger` (asked only when `trigger` is answered yes).
        trigger: The yes-or-no question asked first, for `when="trigger"`.
        reads: What the judge reads beyond the call: `prompt`, `evidence`, `facts`.
    """
    if not A_NAME.match(name):
        raise DeclarationRefused(NOT_A_JUDGE_NAME.format(name=name))
    question = asks.strip()
    if not question:
        raise DeclarationRefused(f"{name}: {NO_QUESTION}")
    picked = _one_of(name, "answer", answer, ANSWERS)
    listed = list(choices)
    if picked == "choice" and len(listed) < FEWEST_CHOICES:
        raise DeclarationRefused(f"{name}: {NO_CHOICES}")
    if picked != "choice" and listed:
        raise DeclarationRefused(f"{name}: {CHOICES_ONLY}")
    runs = _one_of(name, "when", when, WHENS)
    if runs == "trigger" and not trigger.strip():
        raise DeclarationRefused(f"{name}: {NO_TRIGGER}")
    read = [_one_of(name, "reads", one, READS) for one in reads]
    return JudgeDeclaration.model_validate(
        {
            "name": name,
            "question": question,
            "answer": picked,
            "choices": listed,
            "when": runs,
            "trigger": trigger,
            "reads": read,
        }
    ).model_dump()


def own_persona(  # noqa: PLR0913 - one keyword for each thing a caller is
    *,
    name: str,
    goal: str,
    style: str,
    about: str = "",
    facts: Mapping[str, str] | None = None,
    state: Mapping[str, object] | None = None,
    expects: Sequence[str] = (),
    tags: Sequence[str] = (),
    behavior: Mapping[str, object] | None = None,
    llm: str | None = None,
    tts: str | None = None,
    voice: str | None = None,
) -> dict[str, object]:
    """A caller of the agent's own, what a PUT of one takes; refused by sentence when wrong.

    Args:
        name: Lower-case words joined by hyphens: `price-shopper`.
        goal: What the caller wants, in the first person.
        style: How the caller talks.
        about: Who they are, in a line.
        facts: What they say when asked: `{"their name": "Ana García"}`.
        state: The state the call opens in, as the class's fields name it.
        expects: What the agent should do, one line each, judged by `expected-outcome`.
        tags: Words to find the caller by.
        behavior: `interrupts`, `pause_s`, `backchannels`, `speed`, `ambience`, `interferer_db`,
            `packet_loss`: how they act on a spoken line.
        llm: The model that plays them, `vendor/model`; None for the judge model.
        tts: The voice vendor that speaks them, and `voice` the voice; None for the default.
        voice: See `tts`.
    """
    if not A_NAME.match(name):
        raise DeclarationRefused(NOT_A_PERSONA_NAME.format(name=name))
    if not goal.strip():
        raise DeclarationRefused(f"{name}: {NO_GOAL}")
    if not style.strip():
        raise DeclarationRefused(f"{name}: {NO_STYLE}")
    given: dict[str, object] = {
        "name": name,
        "goal": goal,
        "style": style,
        "about": about,
        "facts": dict(facts or {}),
        "state": dict(state or {}),
        "expects": list(expects),
        "tags": list(tags),
        "behavior": dict(behavior or {}),
        "llm": llm,
        "tts": tts,
        "voice": voice,
    }
    try:
        return PersonaDeclaration.model_validate(given).model_dump()
    except ValidationError as failed:
        raise DeclarationRefused(f"{name}: {_said(failed)}") from failed


def judges(
    *, on: Sequence[str] = (), own: Sequence[Mapping[str, object]] = ()
) -> dict[str, object]:
    """The judges the class owns: which of Pinecall's its calls meet, and its own.

    Args:
        on: The names of Pinecall's judges the agent's calls meet; every other is off.
        own: The agent's own, each an `own_judge(...)`; two of one name are refused.
    """
    return {"on": list(on), "own": _each_once("judge", [_judge_checked(one) for one in own])}


def personas(
    *, on: Sequence[str] = (), own: Sequence[Mapping[str, object]] = ()
) -> dict[str, object]:
    """The personas the class owns: which of Pinecall's its runs play, and its own.

    Args:
        on: The names of Pinecall's personas `pinecall simulate` offers; every other is off.
        own: The agent's own, each an `own_persona(...)`; two of one name are refused.
    """
    return {"on": list(on), "own": _each_once("persona", [_persona_checked(one) for one in own])}


def harness_of(cls: type) -> dict[str, object]:
    """What `judges` and `personas` declare, as the declaration sends it; nothing for neither."""
    declared: dict[str, object] = {}
    switches = _switches_of(cls, "judges")
    if switches is not None:
        declared["judges"] = judges(on=switches[0], own=switches[1])
    switches = _switches_of(cls, "personas")
    if switches is not None:
        declared["personas"] = personas(on=switches[0], own=switches[1])
    return declared


# A judge already built reads back as its input, so `judges()` checks it the same way once more.
def _judge_checked(one: Mapping[str, object]) -> dict[str, object]:
    try:
        read = JudgeDeclaration.model_validate(dict(one))
    except ValidationError as failed:
        raise DeclarationRefused(f"{_named(one)}: {_said(failed)}") from failed
    return own_judge(
        name=read.name,
        asks=read.question,
        answer=read.answer,
        choices=read.choices,
        when=read.when,
        trigger=read.trigger,
        reads=read.reads,
    )


def _persona_checked(one: Mapping[str, object]) -> dict[str, object]:
    try:
        read = PersonaDeclaration.model_validate(dict(one))
    except ValidationError as failed:
        raise DeclarationRefused(f"{_named(one)}: {_said(failed)}") from failed
    return own_persona(
        name=read.name,
        goal=read.goal,
        style=read.style,
        about=read.about,
        facts=read.facts,
        state=read.state,
        expects=read.expects,
        tags=read.tags,
        behavior=read.behavior.model_dump(),
        llm=read.llm,
        tts=read.tts,
        voice=read.voice,
    )


def _each_once(what: str, own: list[dict[str, object]]) -> list[dict[str, object]]:
    seen: set[object] = set()
    for one in own:
        if one["name"] in seen:
            raise DeclarationRefused(TWICE.format(what=what, name=one["name"]))
        seen.add(one["name"])
    return own


def _switches_of(cls: type, field: str) -> tuple[list[str], list[Mapping[str, object]]] | None:
    found: object = getattr(cls, field, None)
    if found is None:
        return None
    if not isinstance(found, dict):
        raise DeclarationRefused(NOT_DECLARED_SO)
    declared = cast("dict[str, object]", found)
    on = declared.get("on", [])
    own = declared.get("own", [])
    if not isinstance(on, list) or not isinstance(own, list):
        raise DeclarationRefused(NOT_DECLARED_SO)
    return cast("list[str]", on), cast("list[Mapping[str, object]]", own)


def _named(one: Mapping[str, object]) -> str:
    name = one.get("name")
    return name if isinstance(name, str) else "it"


def _said(failed: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(at) for at in one['loc']) or 'it'}: {one['msg']}" for one in failed.errors()
    )


def _one_of(name: str, field: str, value: str, allowed: tuple[str, ...]) -> str:
    if value not in allowed:
        said = NOT_ONE_OF.format(field=field, value=value, allowed=", ".join(allowed))
        raise DeclarationRefused(f"{name}: {said}")
    return value
