"""A tool's spec and arguments: the schema a model reads, and what it sent, checked against it."""

from typing import Literal

import pytest
from pydantic import BaseModel

from pinecall import DeclarationRefused, ToolFailed
from pinecall._spec import arguments_model, schema_of, spec_of, validated


class Slot(BaseModel):
    """A slot the caller chose."""

    id: str
    title: str


def choose(self: object, slot: Slot, json: str, mode: Literal["cold", "warm"] = "cold") -> None:
    """Choose a slot.

    Args:
        self: the agent
        slot: the slot, whole
        json: a parameter named like a method of pydantic's own
        mode: how
    """


def test_a_literal_is_an_enum_a_model_is_a_nested_object_and_no_title_is_left() -> None:
    schema = schema_of(arguments_model("choose", choose), {"slot": "the slot, whole"})
    assert schema["properties"]["mode"] == {
        "enum": ["cold", "warm"],
        "type": "string",
        "default": "cold",
    }
    assert schema["$defs"]["Slot"] == {
        "description": "A slot the caller chose.",
        "properties": {"id": {"type": "string"}, "title": {"type": "string"}},
        "required": ["id", "title"],
        "type": "object",
    }
    assert schema["properties"]["slot"]["description"] == "the slot, whole"


def test_a_parameter_named_like_a_method_of_pydantic_is_filled_by_its_own_name() -> None:
    model = arguments_model("choose", choose)
    given = {"slot": {"id": "s1", "title": "martes"}, "json": "x"}
    assert validated("choose", model, given) == {"slot": Slot(id="s1", title="martes"), "json": "x"}


def test_a_parameter_left_out_is_left_to_the_methods_own_default() -> None:
    model = arguments_model("choose", choose)
    assert "mode" not in validated(
        "choose", model, {"slot": {"id": "s", "title": "t"}, "json": "x"}
    )


def test_a_nested_value_that_does_not_fit_says_where() -> None:
    model = arguments_model("choose", choose)
    with pytest.raises(ToolFailed, match=r"choose: slot\.title is required"):
        validated("choose", model, {"slot": {"id": "s"}, "json": "x"})


def test_a_parameter_with_no_annotation_is_text_because_that_is_what_a_caller_says() -> None:
    def note(self: object, text) -> None:  # noqa: ANN001 # pyright: ignore[reportMissingParameterType, reportUnknownParameterType]
        """Note."""

    assert schema_of(arguments_model("note", note), {})  # pyright: ignore[reportUnknownArgumentType]["properties"]["text"] == {"type": "string"}


def test_a_name_no_model_can_call_is_refused() -> None:
    with pytest.raises(DeclarationRefused, match="one word a model can call"):
        spec_of("1st", choose, arguments_model("choose", choose), {})


def test_a_type_that_does_not_resolve_is_refused_naming_it() -> None:
    def lost(self: object, slot: "Nowhere") -> None:  # noqa: F821 # pyright: ignore[reportUndefinedVariable, reportUnknownParameterType]
        """Lost."""

    with pytest.raises(DeclarationRefused, match="Nowhere"):
        arguments_model("lost", lost)  # pyright: ignore[reportUnknownArgumentType]
