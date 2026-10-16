"""How a call opens and when the agent may end it, as a class writes them: `improvise`, `words`."""

from dataclasses import dataclass

from pinecall.errors import DeclarationRefused

NO_OPENING = (
    "a greeting is the words, as a string, or improvise for the model's own: "
    'improvise("…") gives it an instruction'
)
NO_ENDING = (
    "hangup is when the model may end the call, in your words, or True whenever it judges the "
    "call done"
)


@dataclass(frozen=True)
class Improvised:
    """The model opens the call: on its prompt alone, or with an instruction for this opening."""

    instruction: str = ""
    interruptible: bool | None = None


@dataclass(frozen=True)
class Words:
    """Words said as written, with whether the caller may cut them short."""

    text: str
    interruptible: bool | None = None


def improvise(instruction: str = "", *, interruptible: bool | None = None) -> Improvised:
    """Let the model open the call, on its prompt alone or with an instruction for the opening.

    Args:
        instruction: What the model is told about this opening; empty, it opens on its prompt.
        interruptible: Whether the caller may cut the opening short; by default they cannot.
    """
    return Improvised(instruction, interruptible)


def words(text: str, *, interruptible: bool | None = None) -> Words:
    """Words said as written, when the caller may cut them short: `words("…", interruptible=True)`.

    Args:
        text: The opening, said as written.
        interruptible: Whether the caller may cut the opening short; by default they cannot.
    """
    return Words(text, interruptible)


def greeting_of(opening: object) -> dict[str, object]:
    """An opening as the wire says it: words to `say`, or a `reply` the model opens on."""
    if opening is improvise:
        return {"reply": ""}
    if isinstance(opening, str):
        return {"say": opening}
    if isinstance(opening, Improvised):
        return _interruptible({"reply": opening.instruction}, given=opening.interruptible)
    if isinstance(opening, Words):
        return _interruptible({"say": opening.text}, given=opening.interruptible)
    raise DeclarationRefused(NO_OPENING)


def hangup_of(ending: object) -> dict[str, object]:
    """When the model may end the call, as the wire says it: an empty `when` is whenever."""
    if ending is True:
        return {"when": ""}
    if isinstance(ending, str) and ending.strip():
        return {"when": ending}
    raise DeclarationRefused(NO_ENDING)


def _interruptible(said: dict[str, object], *, given: bool | None) -> dict[str, object]:
    return said if given is None else {**said, "allow_interruptions": given}
