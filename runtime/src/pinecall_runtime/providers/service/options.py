"""What a vendor's plugin takes for a stage, read off its constructor: each argument a form can draw, nothing else."""

import dataclasses
import inspect
import types
import typing
from collections.abc import Iterator, Sequence
from typing import Any, Literal

from livekit.agents.types import NotGiven

from pinecall_runtime.agents.declaration import Modality
from pinecall_runtime.providers.schemas import OptionKind, PluginOption, PluginOptions
from pinecall_runtime.providers.service.plugins import THE_HINTS, THE_KEY, THE_LANGUAGE, THE_TERMS, THE_VOICE, Running
from pinecall_runtime.providers.service.shaping import dataclass_in
from pinecall_runtime.providers.service.stages import SAMPLING, THE_MODEL, class_of

# What the settings set elsewhere, or the call fills itself: never an option of its own.
THE_KNOBS = frozenset({*THE_KEY, *THE_VOICE, *THE_LANGUAGE, *THE_HINTS, *THE_TERMS, THE_MODEL, "temperature"})
# Arguments no form can fill: the plugin's own plumbing.
PLUMBING = frozenset({"self", "args", "kwargs", "http_session", "client", "credentials", "session"})
SCALARS: dict[type, OptionKind] = {str: "text", bool: "boolean", int: "integer", float: "number"}


def options_of(modality: Modality, vendor: str, builds: str | None) -> PluginOptions:
    """The plugin's arguments for the stage as a form draws them, of the class `builds` names, else the stage's."""
    made = class_of(modality, Running(vendor, "", builds=builds))
    found = [option for parameter in _parameters(made) for option in _drawn(parameter, None)]
    return PluginOptions(vendor=vendor, modality=modality, builds=made.__name__, options=found)


def _parameters(made: type) -> list[inspect.Parameter]:
    try:
        return list(inspect.signature(made, eval_str=True).parameters.values())
    except (NameError, TypeError, ValueError):
        return []


# One argument as the form draws it: a scalar, a closed list, a list of text, a JSON object; one the
# settings set elsewhere, or that no form can type, is left out; one that is a dataclass is its fields.
def _drawn(parameter: inspect.Parameter, inside: str | None) -> Iterator[PluginOption]:
    name = parameter.name
    if name.startswith("_") or name in PLUMBING or name in THE_KNOBS or name in SAMPLING - {"top_p", "top_k"}:
        return
    if parameter.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
        return
    declared = parameter.annotation
    shape = dataclass_in(declared)
    if shape is not None and inside is None:
        hints = typing.get_type_hints(shape)
        # A field with no default would make the whole object required: an object is drawn by what it defaults.
        for field in dataclasses.fields(shape):
            if field.default is dataclasses.MISSING:
                continue
            default = field.default
            yield from _drawn(
                inspect.Parameter(
                    field.name, inspect.Parameter.KEYWORD_ONLY, default=default, annotation=hints.get(field.name, Any)
                ),
                name,
            )
        return
    kind, choices, is_open = _kind_of(declared)
    if kind is None:
        return
    default = parameter.default
    required = default is inspect.Parameter.empty
    yield PluginOption(
        name=name,
        inside=inside,
        kind=kind,
        choices=choices,
        open=is_open,
        default=None if required or isinstance(default, NotGiven) else _plain(default),
        required=required,
    )


def _kind_of(declared: object) -> tuple[OptionKind | None, list[str], bool]:
    members = [one for one in _members(declared) if one is not type(None) and one is not NotGiven]
    choices = [
        str(value) for member in members if typing.get_origin(member) is Literal for value in typing.get_args(member)
    ]
    plain = [member for member in members if typing.get_origin(member) is not Literal]
    # A closed list, alone or beside plain text, is a choice; beside a number or a flag it is that.
    if choices and all(member is str for member in plain):
        return "choice", choices, str in plain
    if any(typing.get_origin(member) in (list, tuple) for member in plain) or list in plain:
        return "list", [], False
    if any(typing.get_origin(member) is dict or member is dict for member in plain):
        return "json", [], False
    scalars: list[OptionKind] = [SCALARS[member] for member in plain if isinstance(member, type) and member in SCALARS]
    if not scalars or len(scalars) != len(plain):
        return None, [], False
    if "text" in scalars:
        return "text", [], False
    if "number" in scalars:
        return "number", [], False
    return scalars[0], [], False


def _members(declared: object) -> list[object]:
    if declared is inspect.Parameter.empty or declared is Any:
        return []
    if isinstance(declared, types.UnionType) or typing.get_origin(declared) is typing.Union:
        return [member for one in typing.get_args(declared) for member in _members(one)]
    return [declared]


def _plain(value: object) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_plain(one) for one in typing.cast("Sequence[object]", value)]
    return None
