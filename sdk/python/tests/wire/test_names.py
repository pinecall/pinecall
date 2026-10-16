"""Tests for the runtime's words: JSON nests as deep as it likes, and a world is one of two."""

import pytest
from pydantic import TypeAdapter, ValidationError

from pinecall.wire._names import Env, JsonObject


def test_a_json_object_nests_lists_and_objects_as_deep_as_it_likes() -> None:
    nested: JsonObject = {"a": [{"b": None, "c": [1, 2.5, "x", True]}]}
    assert TypeAdapter(JsonObject).validate_python(nested) == nested


def test_a_value_json_cannot_carry_is_refused() -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(JsonObject).validate_python({"a": object()})


def test_a_world_is_production_or_the_sandbox_and_nothing_else() -> None:
    assert TypeAdapter(Env).validate_python("sandbox") == "sandbox"
    with pytest.raises(ValidationError):
        TypeAdapter(Env).validate_python("staging")
