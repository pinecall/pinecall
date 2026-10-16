"""The state a class declares: annotations are fields, a property derived, every write authored."""

from functools import cached_property
from typing import ClassVar, Literal

import pytest

from pinecall import Agent, DeclarationRefused, NotAStage, UnauthoredWrite, state
from pinecall._author import writing_as
from pinecall._state import FIELDS, visibilities_of


class Tienda(Agent):
    """Una tienda que recuerda un carrito."""

    stage: Literal["browsing", "checkout"] = "browsing"
    cart: list[str] = []  # noqa: RUF012 - a field's opening value, copied for every call
    customer: str | None = state(pii=True)
    city: str = state("Madrid", visibility="public")
    note: str | None
    shelves: ClassVar[int] = 4
    _cache: dict[str, str] = {}  # noqa: RUF012 - not state: it starts with _

    @property
    def has_cart(self) -> bool:
        """Whether anything is in the cart."""
        return bool(self.cart)

    @cached_property
    def catalog(self) -> list[str]:
        """A collaborator, not state."""
        return ["café", "té"]


@pytest.fixture
def tienda() -> Tienda:
    return Tienda().seal()


def test_a_field_opens_at_the_value_the_class_gave_it_and_none_without_one(tienda: Tienda) -> None:
    assert (tienda.cart, tienda.stage, tienda.customer, tienda.city) == (
        [],
        "browsing",
        None,
        "Madrid",
    )
    assert tienda.note is None


def test_every_call_gets_a_list_of_its_own_and_not_one_shared_by_all_of_them(
    tienda: Tienda,
) -> None:
    tienda.cart.append("café")
    assert Tienda().cart == []


def test_a_write_outside_a_tool_is_refused_by_name(tienda: Tienda) -> None:
    with pytest.raises(UnauthoredWrite, match="customer"):
        tienda.customer = "Marta"


def test_a_write_carries_its_author_and_what_the_field_held_before(tienda: Tienda) -> None:
    with writing_as("add"):
        tienda.cart = ["café"]
        tienda.stage = "checkout"
    assert [(c.author, c.field, c.before, c.after) for c in tienda.changes()] == [
        ("add", "cart", [], ["café"]),
        ("add", "stage", "browsing", "checkout"),
    ]


def test_the_opening_values_are_the_baseline_and_not_a_change() -> None:
    assert Tienda().seal().changes() == []


def test_before_the_seal_a_write_needs_no_author_and_is_not_recorded() -> None:
    tienda = Tienda()
    tienda.customer = "Marta"
    assert tienda.seal().changes() == []


def test_writing_the_same_value_again_is_not_a_change(tienda: Tienda) -> None:
    with writing_as("the test"):
        tienda.city = "Madrid"
    assert tienda.changes() == []


def test_a_stage_the_literal_does_not_hold_is_refused(tienda: Tienda) -> None:
    with pytest.raises(NotAStage, match="browsing, checkout"):
        tienda.restore({"stage": "paying"})


def test_a_property_is_a_derived_field_in_the_snapshot_and_cannot_be_assigned(
    tienda: Tienda,
) -> None:
    assert tienda.snapshot()["has_cart"] is False
    with pytest.raises(AttributeError):
        tienda.has_cart = True  # pyright: ignore[reportAttributeAccessIssue]


def test_a_snapshot_is_the_state_and_nothing_else(tienda: Tienda) -> None:
    assert tienda.snapshot() == {
        "stage": "browsing",
        "cart": [],
        "customer": None,
        "city": "Madrid",
        "note": None,
        "has_cart": False,
    }


def test_restoring_a_snapshot_clears_a_field_the_snapshot_leaves_out(tienda: Tienda) -> None:
    tienda.restore({"stage": "checkout", "cart": ["té"]})
    assert (tienda.stage, tienda.cart, tienda.city) == ("checkout", ["té"], None)


def test_starting_in_a_state_sets_what_it_names_and_keeps_the_rest(tienda: Tienda) -> None:
    tienda.start_in({"customer": "Marta"})
    assert (tienda.customer, tienda.city) == ("Marta", "Madrid")


def test_collapsing_keeps_one_sentence_where_the_changes_were(tienda: Tienda) -> None:
    with writing_as("add"):
        tienda.cart = ["café"]
    tienda.collapse("El cliente pidió un café.")
    assert [(c.field, c.after) for c in tienda.changes()] == [
        ("@summary", "El cliente pidió un café.")
    ]
    assert tienda.cart == ["café"]


def test_a_listener_hears_every_recorded_write_until_it_stops(tienda: Tienda) -> None:
    heard: list[str] = []
    stop = tienda.on_change(lambda change: heard.append(change.field))
    with writing_as("the test"):
        tienda.customer = "Marta"
        stop()
        tienda.customer = "Ana"
    assert heard == ["customer"]


def test_only_the_fields_that_said_who_may_see_them_travel_with_a_visibility() -> None:
    assert [(spec.name, spec.visibility) for spec in visibilities_of(getattr(Tienda, FIELDS))] == [
        ("customer", "pii"),
        ("city", "public"),
    ]


def test_a_stage_with_no_value_opens_at_the_first_one_written() -> None:
    class Fases(Agent):
        """Dos fases."""

        stage: Literal["one", "two"]

    assert Fases().stage == "one"


def test_a_stage_that_is_not_a_literal_of_its_values_is_refused() -> None:
    def declared() -> type[Agent]:
        class Fases(Agent):
            """Sin valores."""

            stage: str = "one"

        return Fases

    with pytest.raises(DeclarationRefused, match="Literal"):
        declared()


def test_a_field_named_like_something_the_agent_itself_has_is_refused() -> None:
    body = {"__doc__": "Un campo que choca.", "__annotations__": {"snapshot": str}, "snapshot": ""}
    with pytest.raises(DeclarationRefused, match="`snapshot` is a name the agent itself uses"):
        type("Choca", (Agent,), body)


def test_a_field_that_is_both_pii_and_public_is_refused() -> None:
    with pytest.raises(DeclarationRefused, match="pii or public"):
        state(pii=True, visibility="public")


def test_a_subclass_keeps_its_parents_fields_and_adds_its_own() -> None:
    class Grande(Tienda):
        """Una tienda con almacén."""

        stock: int = 0

    assert set(Grande().snapshot()) == {*Tienda().snapshot(), "stock"}
