"""One tool as the gateway receives it, and what is refused before a model ever sees it."""

import inspect
import re
import typing
from collections.abc import Callable, Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model

from pinecall import _doc
from pinecall.errors import DeclarationRefused, ToolFailed
from pinecall.wire.parts import ToolSpec

A_NAME_A_MODEL_CAN_CALL = re.compile(r"[A-Za-z][A-Za-z0-9_]*")

# A model fills a JSON object by name: a parameter it cannot name, it cannot fill.
FILLED_BY_NAME = (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)

# The arguments are validated once more by the model the schema came from; a key nobody declared
# is refused, as the schema says.
CLOSED = ConfigDict(extra="forbid", validate_by_alias=True, validate_by_name=False)


def arguments_model(name: str, method: Callable[..., object]) -> type[BaseModel]:
    """The tool's parameters as a pydantic model: the schema the model reads and the validator."""
    try:
        hints = typing.get_type_hints(method)
    except NameError as error:
        raise DeclarationRefused(
            f"tool {name}: a parameter's type does not resolve: {error}"
        ) from error
    fields: dict[str, Any] = {}
    for index, (called, parameter) in enumerate(inspect.signature(method).parameters.items()):
        if called == "self":
            continue
        if parameter.kind not in FILLED_BY_NAME:
            raise DeclarationRefused(
                f"tool {name}: a model fills a JSON object by name, so every parameter is one it "
                f"can name; {parameter} is not"
            )
        default = ... if parameter.default is inspect.Parameter.empty else parameter.default
        # Stored under a name of ours, so a parameter called `json` or `copy` never shadows the
        # model's own; the model and the schema know it by its own name.
        fields[f"p{index}"] = (hints.get(called, str), Field(default, alias=called))
    return create_model(f"{name}_arguments", __config__=CLOSED, **fields)


def spec_of(
    name: str, method: Callable[..., object], arguments: type[BaseModel], said: Mapping[str, object]
) -> ToolSpec:
    """Build the spec the gateway receives, refusing what it would refuse."""
    if not A_NAME_A_MODEL_CAN_CALL.fullmatch(name):
        raise DeclarationRefused(f"a tool name is one word a model can call, not {name}")
    doc = inspect.getdoc(method)
    description = _doc.one_line(doc)
    if description is None:
        raise DeclarationRefused(
            f"tool {name}: without a docstring no model can choose it;"
            ' write one: """Books the hour."""'
        )
    parameters = schema_of(arguments, _doc.arguments_of(doc))
    pii = said.get("pii")
    if isinstance(pii, tuple):
        named = typing.cast("tuple[str, ...]", pii)
        unknown = [one for one in named if one not in parameters["properties"]]
        if unknown:
            raise DeclarationRefused(
                f"tool {name}: pii names parameters the tool has; unknown: {', '.join(unknown)}"
            )
    spec: dict[str, object] = {
        "name": name,
        "description": description,
        "parameters": parameters,
        "side_effect": "irreversible" if said.get("confirm") else "read",
    }
    spec |= {key: said[key] for key in ("confirm", "announce", "pii") if said.get(key) is not None}
    if said.get("timeout") is not None:
        spec["timeout_s"] = said["timeout"]
    try:
        return ToolSpec.model_validate(spec)
    except ValidationError as error:
        raise DeclarationRefused(f"tool {name}: {error}") from error


def schema_of(arguments: type[BaseModel], described: Mapping[str, str]) -> dict[str, Any]:
    """The JSON Schema of the arguments, closed, with what the docstring says of each one."""
    schema = untitled(arguments.model_json_schema(by_alias=True))
    properties: dict[str, Any] = schema.setdefault("properties", {})
    for called, text in described.items():
        if called in properties:
            properties[called]["description"] = text
    schema.setdefault("required", [])
    schema["additionalProperties"] = False
    return schema


def untitled(schema: dict[str, Any]) -> dict[str, Any]:
    """The schema without pydantic's titles, which repeat the names; a property's name stays."""
    kept: dict[str, Any] = {}
    for key, value in schema.items():
        if key == "title" and isinstance(value, str):
            continue
        if key in ("properties", "$defs") and isinstance(value, dict):
            named = typing.cast("dict[str, Any]", value)
            kept[key] = {
                one: untitled(typing.cast("dict[str, Any]", inner)) for one, inner in named.items()
            }
        elif isinstance(value, dict):
            kept[key] = untitled(typing.cast("dict[str, Any]", value))
        elif isinstance(value, list):
            items = typing.cast("list[Any]", value)
            kept[key] = [
                untitled(typing.cast("dict[str, Any]", one)) if isinstance(one, dict) else one
                for one in items
            ]
        else:
            kept[key] = value
    return kept


def validated(
    name: str, arguments: type[BaseModel], given: Mapping[str, object]
) -> dict[str, object]:
    """The arguments the model sent, checked and converted; one left out keeps its default."""
    try:
        checked = arguments.model_validate(dict(given))
    except ValidationError as error:
        raise ToolFailed(f"{name}: {'; '.join(complaint(one) for one in error.errors())}") from None
    return {
        str(field.alias): getattr(checked, key)
        for key, field in type(checked).model_fields.items()
        if key in checked.model_fields_set
    }


def complaint(error: Mapping[str, Any]) -> str:
    """One validation error as the model reads it."""
    where = ".".join(str(part) for part in error["loc"])
    if error["type"] == "missing":
        return f"{where} is required"
    if error["type"] == "extra_forbidden":
        return f"it takes no {where}"
    return f"{where}: {error['msg']}"
