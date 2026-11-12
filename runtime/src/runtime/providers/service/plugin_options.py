"""A plugin's constructor as a form: each argument a form can draw for a stage, nothing the settings set elsewhere."""

import dataclasses
import inspect
import types
import typing
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, Literal, TypeIs

from livekit.agents.types import NotGiven

from runtime.enums import Stage
from runtime.providers.service import plugins
from runtime.providers.service.llm_requests import SAMPLING
from runtime.providers.service.signatures import (
    THE_HINTS,
    THE_KEY,
    THE_LANGUAGE,
    THE_MODEL,
    THE_TERMS,
    THE_VOICE,
    class_of,
    dataclass_in,
)
from runtime.providers.stage import Running

type OptionKind = Literal["text", "number", "integer", "boolean", "choice", "list", "json"]

# What the settings set elsewhere, or the call fills itself: never an option of its own.
THE_KNOBS = frozenset({*THE_KEY, *THE_VOICE, *THE_LANGUAGE, *THE_HINTS, *THE_TERMS, THE_MODEL, "temperature"})
# Arguments no form can fill: the plugin's own plumbing.
PLUMBING = frozenset({"self", "args", "kwargs", "http_session", "client", "credentials", "session"})
SCALARS: dict[type, OptionKind] = {str: "text", bool: "boolean", int: "integer", float: "number"}


@dataclass(frozen=True, slots=True)
class Option:
    """One keyword argument a vendor's plugin takes for a stage, as a form draws it."""

    name: str
    # The options object it sits in, where the plugin takes one (`params`, `voice_settings`); else None.
    inside: str | None
    kind: OptionKind
    # A closed list the plugin names; with `open`, any other text is taken too.
    choices: list[str] = field(default_factory=list[str])
    open: bool = False
    default: Any = None
    required: bool = False


@dataclass(frozen=True, slots=True)
class Form:
    """What a vendor's plugin takes for a stage, the settings' knobs left out."""

    vendor: str
    modality: Stage
    builds: str
    options: list[Option]


# Read off the plugin's constructor, so a console draws a form a plugin changes with its version.
def form_of(stage: Stage, vendor: str, builds: str | None) -> Form:
    """The plugin's arguments for the stage as a form draws them, of the class `builds` names, else the stage's."""
    named = plugins.vendor_doing(plugins.parse_vendor(vendor), stage)
    made = class_of(stage, Running(named, "", builds=builds))
    found = [option for parameter in _parameters_of(made) for option in _draw(parameter, None)]
    return Form(vendor=named, modality=stage, builds=made.__name__, options=found)


def _parameters_of(made: type) -> list[inspect.Parameter]:
    try:
        return list(inspect.signature(made, eval_str=True).parameters.values())
    except (NameError, TypeError, ValueError):
        return []


# One argument as the form draws it: a scalar, a closed list, a list of text, a JSON object; one the
# settings set elsewhere, or that no form can type, is left out; one that is a dataclass is its fields.
def _draw(parameter: inspect.Parameter, inside: str | None) -> Iterator[Option]:
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
        for each in dataclasses.fields(shape):
            if each.default is dataclasses.MISSING:
                continue
            default = each.default
            yield from _draw(
                inspect.Parameter(
                    each.name, inspect.Parameter.KEYWORD_ONLY, default=default, annotation=hints.get(each.name, Any)
                ),
                name,
            )
        return
    kind, choices, is_open = _kind_of(declared)
    if kind is None:
        return
    default = parameter.default
    required = default is inspect.Parameter.empty
    yield Option(
        name=name,
        inside=inside,
        kind=kind,
        choices=choices,
        open=is_open,
        default=None if required or isinstance(default, NotGiven) else _plain(default),
        required=required,
    )


def _kind_of(declared: object) -> tuple[OptionKind | None, list[str], bool]:
    members = [one for one in _members_of(declared) if one is not type(None) and one is not NotGiven]
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


def _members_of(declared: object) -> list[object]:
    if declared is inspect.Parameter.empty or declared is Any:
        return []
    if isinstance(declared, types.UnionType) or typing.get_origin(declared) is typing.Union:
        return [member for one in typing.get_args(declared) for member in _members_of(one)]
    return [declared]


def _plain(value: object) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return [_plain(one) for one in value] if _is_a_sequence(value) else None


# What a default of a plugin's argument hands back is typed as nothing; this says what it is.
def _is_a_sequence(value: object) -> TypeIs[list[object] | tuple[object, ...]]:
    return isinstance(value, list | tuple)
