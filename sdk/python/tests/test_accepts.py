"""The outside events a class accepts: by name and sender, inherited, refused when wrong."""

from collections.abc import Mapping, Sequence
from typing import ClassVar

import pytest

from pinecall import Agent, DeclarationRefused
from pinecall._accepts import specs_of, takes
from pinecall.wire._names import EventSource


class Tienda(Agent):
    """Una tienda que escucha a su backend."""

    accepts: ClassVar[Mapping[str, Sequence[EventSource]]] = {
        "cart.changed": ["app"],
        "page.seen": ["participant", "app"],
    }


def events(cls: type[Agent]) -> dict[str, tuple[EventSource, ...]]:
    found: dict[str, tuple[EventSource, ...]] = getattr(cls, "_pinecall_events")  # noqa: B009 - the class's own
    return found


def test_an_event_reaches_the_class_only_from_the_senders_it_names() -> None:
    declared = getattr(Tienda, "_pinecall_events")  # noqa: B009 - the class's own
    assert takes(declared, "cart.changed", "app")
    assert not takes(declared, "cart.changed", "participant")
    assert not takes(declared, "stock.low", "app")


def test_the_events_travel_as_agent_configure_carries_them() -> None:
    assert [spec.written() for spec in specs_of(events(Tienda))] == [
        {"name": "cart.changed", "from": ["app"]},
        {"name": "page.seen", "from": ["participant", "app"]},
    ]


def test_a_subclass_keeps_its_parents_events_and_one_it_names_again_replaces_its_senders() -> None:
    class Grande(Tienda):
        """Una tienda que también oye al navegador."""

        # Unannotated, as most classes write it: the base's ClassVar is what pyright reads.
        accepts = {"cart.changed": ["participant"], "stock.low": ["app"]}  # noqa: RUF012

    assert events(Grande) == {
        "cart.changed": ("participant",),
        "page.seen": ("participant", "app"),
        "stock.low": ("app",),
    }


@pytest.mark.parametrize(
    ("accepts", "said"),
    [
        ({"cart.changed": ["browser"]}, "'browser' sends nothing"),
        ({"cart.changed": []}, "names who sends it"),
        (["cart.changed"], "names each event and who sends it"),
    ],
)
def test_an_event_from_nobody_or_a_list_with_no_senders_is_refused(
    accepts: object, said: str
) -> None:
    with pytest.raises(DeclarationRefused, match=said):
        type("Mala", (Agent,), {"__doc__": "Mal declarada.", "accepts": accepts})
