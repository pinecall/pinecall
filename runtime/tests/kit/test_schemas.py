"""A response body built from what a service returns: its attributes read at every depth."""

from dataclasses import dataclass

from runtime.kit.schemas import Row
from runtime.wire.base import WireModel


class Opening(WireModel):
    """A shape of the wire, which reads no attributes by itself."""

    say: str | None = None


class Answer(Row):
    """A body with a shape of the wire inside it."""

    agent: str
    opening: Opening | None


@dataclass(frozen=True, slots=True)
class Opens:
    """What a service holds of the opening."""

    say: str | None


@dataclass(frozen=True, slots=True)
class Found:
    """What a service returns."""

    agent: str
    opening: Opens | None


def test_a_body_reads_a_nested_shape_of_the_wire_from_what_the_service_holds() -> None:
    """The row's attributes and, inside it, the attributes of what a wire shape is built from."""
    assert Answer.of(Found("support", Opens("Hola."))) == Answer(agent="support", opening=Opening(say="Hola."))
    assert Answer.of(Found("support", None)).opening is None


def test_a_body_is_built_from_a_mapping_as_from_a_row() -> None:
    """A mapping is read by its keys, a nested one too."""
    assert Answer.of({"agent": "support", "opening": {"say": "Hola."}}).opening == Opening(say="Hola.")
