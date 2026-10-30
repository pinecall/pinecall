"""The judges and the personas a class owns, and the folders beside the class read into them."""

import inspect
import json
import re
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from pydantic import ValidationError

from pinecall.errors import DeclarationRefused
from pinecall.wire.judging import JudgeDeclaration, PersonaDeclaration

# The name a judge or a persona is called by: lower-case words joined by hyphens.
A_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

ANSWERS = ("verdict", "choice", "score")
WHENS = ("always", "simulations", "trigger")
READS = ("prompt", "evidence", "facts")
# Fewer than two is not a choice.
FEWEST_CHOICES = 2

NOT_A_PAGE = "a judge opens with its front matter between two --- lines, and the question below"
NO_QUESTION = "a judge asks a question of a call: write one below the front matter"
NO_CHOICES = "a judge that answers one of several needs at least two choices"
CHOICES_ONLY = "only a judge that answers one of several takes choices"
NO_TRIGGER = "a judge that runs on a trigger needs the trigger's question"
NOT_A_JUDGE_NAME = (
    '"{name}" is not a judge\'s name: lower-case words joined by hyphens, like offers-next-slot'
)
ANOTHER_JUDGE_NAME = (
    "its front matter says name: {named}, and the file is {shown}: the file's name is the judge's"
)
NOT_JSON = "not JSON: {why}"
NOT_A_PERSONA = "a persona is a JSON object with a goal and a style"
NO_GOAL = "a persona wants something: write its goal, in the first person"
NO_STYLE = "a persona talks some way: write its style"
NOT_A_PERSONA_NAME = (
    '"{name}" is not a persona\'s name: lower-case words joined by hyphens, like price-shopper'
)
ANOTHER_PERSONA_NAME = (
    "it says its name is {named}, and the file is {shown}: the file's name is the persona's"
)
NOT_ONE_OF = '{field} is "{value}", not one of {allowed}'
UNDECLARED_JUDGES = (
    "{folder} holds {count} judge(s) and the class declares none: "
    'judges = judges(on=["consent", …]) declares them, and which of Pinecall\'s run'
)
UNDECLARED_PERSONAS = (
    "{folder} holds {count} persona(s) and the class declares none: "
    'personas = personas(on=["in-a-hurry", …]) declares them, and which of Pinecall\'s play'
)
NOT_DECLARED_SO = "judges and personas are declared with judges(on=[…]) and personas(on=[…])"


def judges(*, on: Sequence[str] = ()) -> dict[str, object]:
    """The judges the class owns: which of Pinecall's its calls meet; its own are `judges/*.md`.

    Args:
        on: The names of Pinecall's judges the agent's calls meet; every other is off.
    """
    return {"on": list(on)}


def personas(*, on: Sequence[str] = ()) -> dict[str, object]:
    """The personas the class owns: which of Pinecall's its runs play; its own are the files.

    Its own callers are `test/personas/<name>.json`, one each, beside the class.

    Args:
        on: The names of Pinecall's personas `pinecall simulate` offers; every other is off.
    """
    return {"on": list(on)}


def folder_of(cls: type) -> Path | None:
    """The folder the class's file is in; None for a class with no file."""
    try:
        return Path(inspect.getfile(cls)).resolve().parent
    except (TypeError, OSError):
        return None


# A folder with files and no declaration is refused: a judge nobody declared would run on no
# call, and the sentence says what to write.
def harness_of(cls: type, folder: Path | None) -> dict[str, object]:
    """What `judges` and `personas` declare, the folders beside the class read into each `own`."""
    declared: dict[str, object] = {}
    judge_files = [] if folder is None else read_judge_files(folder / "judges")
    own_judges = _switches_of(cls, "judges")
    if own_judges is not None:
        declared["judges"] = _declared(own_judges, judge_files)
    elif judge_files:
        where = f"{folder}/judges"
        raise DeclarationRefused(UNDECLARED_JUDGES.format(folder=where, count=len(judge_files)))
    persona_files = [] if folder is None else read_persona_files(folder / "test" / "personas")
    own_personas = _switches_of(cls, "personas")
    if own_personas is not None:
        declared["personas"] = _declared(own_personas, persona_files)
    elif persona_files:
        where = f"{folder}/test/personas"
        count = len(persona_files)
        raise DeclarationRefused(UNDECLARED_PERSONAS.format(folder=where, count=count))
    return declared


def read_judge_files(folder: Path) -> list[dict[str, object]]:
    """Every `<name>.md` under the folder as a judge, refused by sentence; none for no folder."""
    if not folder.is_dir():
        return []
    paths = sorted(path for path in folder.iterdir() if path.suffix == ".md")
    return [judge_of(path, path.read_text(encoding="utf-8")).model_dump() for path in paths]


def read_persona_files(folder: Path) -> list[dict[str, object]]:
    """Every `<name>.json` under the folder as a persona, refused by sentence; none for none."""
    if not folder.is_dir():
        return []
    paths = sorted(path for path in folder.iterdir() if path.suffix == ".json")
    return [persona_of(path, path.read_text(encoding="utf-8")).model_dump() for path in paths]


def judge_of(path: Path, text: str) -> JudgeDeclaration:
    """A judge file: the library's format, front matter between two `---` lines, the question."""
    shown = path.name
    name = path.stem
    fields, body = _page(shown, text)
    if not A_NAME.match(name):
        raise DeclarationRefused(f"{shown}: {NOT_A_JUDGE_NAME.format(name=name)}")
    if "name" in fields and fields["name"] != name:
        said = ANOTHER_JUDGE_NAME.format(named=fields["name"], shown=shown)
        raise DeclarationRefused(f"{shown}: {said}")
    question = body.strip()
    if not question:
        raise DeclarationRefused(f"{shown}: {NO_QUESTION}")
    answer = _one_of(shown, "answer", fields.get("answer", "verdict"), ANSWERS)
    choices = _listed(fields.get("choices", ""))
    if answer == "choice" and len(choices) < FEWEST_CHOICES:
        raise DeclarationRefused(f"{shown}: {NO_CHOICES}")
    if answer != "choice" and choices:
        raise DeclarationRefused(f"{shown}: {CHOICES_ONLY}")
    when = _one_of(shown, "when", fields.get("when", fields.get("on", "always")), WHENS)
    trigger = fields.get("trigger", "")
    if when == "trigger" and not trigger.strip():
        raise DeclarationRefused(f"{shown}: {NO_TRIGGER}")
    reads = [_one_of(shown, "reads", read, READS) for read in _listed(fields.get("reads", ""))]
    return JudgeDeclaration.model_validate(
        {
            "name": name,
            "question": question,
            "answer": answer,
            "choices": choices,
            "when": when,
            "trigger": trigger,
            "reads": reads,
        }
    )


def persona_of(path: Path, text: str) -> PersonaDeclaration:
    """A persona file: JSON, what `PUT …/personas/{name}` takes, the name being the file's."""
    shown = path.name
    name = path.stem
    if not A_NAME.match(name):
        raise DeclarationRefused(f"{shown}: {NOT_A_PERSONA_NAME.format(name=name)}")
    try:
        raw: object = json.loads(text)
    except ValueError as failed:
        raise DeclarationRefused(f"{shown}: {NOT_JSON.format(why=failed)}") from failed
    if not isinstance(raw, dict):
        raise DeclarationRefused(f"{shown}: {NOT_A_PERSONA}")
    given: dict[str, object] = dict(raw)  # pyright: ignore[reportUnknownArgumentType]
    goal = given.get("goal")
    if not isinstance(goal, str) or not goal.strip():
        raise DeclarationRefused(f"{shown}: {NO_GOAL}")
    style = given.get("style")
    if not isinstance(style, str) or not style.strip():
        raise DeclarationRefused(f"{shown}: {NO_STYLE}")
    if "name" in given and given["name"] != name:
        said = ANOTHER_PERSONA_NAME.format(named=given["name"], shown=shown)
        raise DeclarationRefused(f"{shown}: {said}")
    try:
        return PersonaDeclaration.model_validate({**given, "name": name})
    except ValidationError as failed:
        said = "; ".join(
            f"{'.'.join(str(at) for at in one['loc']) or 'it'}: {one['msg']}"
            for one in failed.errors()
        )
        raise DeclarationRefused(f"{shown}: {said}") from failed


def _switches_of(cls: type, field: str) -> dict[str, object] | None:
    found: object = getattr(cls, field, None)
    if found is None:
        return None
    if not isinstance(found, dict):
        raise DeclarationRefused(NOT_DECLARED_SO)
    return cast("dict[str, object]", found)


def _declared(switches: dict[str, object], files: list[dict[str, object]]) -> dict[str, object]:
    on = switches.get("on", [])
    own = switches.get("own", [])
    if not isinstance(on, list) or not isinstance(own, list):
        raise DeclarationRefused(NOT_DECLARED_SO)
    listed = cast("list[object]", on)
    kept = cast("list[object]", own)
    return {"on": listed, "own": [*kept, *files]}


def _page(shown: str, text: str) -> tuple[dict[str, str], str]:
    _, opened, rest = text.partition("---\n")
    head, closed, body = rest.partition("\n---\n")
    if not opened or not closed:
        raise DeclarationRefused(f"{shown}: {NOT_A_PAGE}")
    fields: dict[str, str] = {}
    for line in head.splitlines():
        key, colon, value = line.partition(":")
        if colon and line.strip():
            fields[key.strip()] = re.sub(r"\s+#.*$", "", value).strip()
    return fields, body


# A list is `[a, b]` or `a, b`; the library writes the second.
def _listed(value: str) -> list[str]:
    return [item.strip() for item in value.strip("[]").split(",") if item.strip()]


def _one_of(shown: str, field: str, value: str, allowed: tuple[str, ...]) -> str:
    if value not in allowed:
        said = NOT_ONE_OF.format(field=field, value=value, allowed=", ".join(allowed))
        raise DeclarationRefused(f"{shown}: {said}")
    return value
