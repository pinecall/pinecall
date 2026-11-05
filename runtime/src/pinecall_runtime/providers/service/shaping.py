"""A plugin's arguments shaped as it declares them: its one options object found, and a mapping built into it."""

import dataclasses
import inspect
import types
import typing
from collections.abc import Mapping

from pinecall_runtime.kit.text import a_mapping


# The argument whose declared type is a dataclass, and that dataclass's fields.
def options_object(made: type) -> tuple[str, frozenset[str]] | None:
    """The argument whose declared type is a dataclass, and that dataclass's fields; None when it takes none."""
    try:
        declared = inspect.signature(made, eval_str=True).parameters
    except (NameError, TypeError, ValueError):
        return None
    for name, parameter in declared.items():
        shape = dataclass_in(parameter.annotation)
        if shape is not None:
            return name, frozenset(field.name for field in dataclasses.fields(shape))
    return None


# A plugin that takes its options as one object (`params=STTOptions(...)`) is given that object,
# built from the row's mapping field by field, however deep.
def shaped(made: type, given: Mapping[str, object]) -> dict[str, object]:
    """The arguments with each mapping built into the dataclass the plugin declares for it, however deep."""
    try:
        declared = {
            name: parameter.annotation for name, parameter in inspect.signature(made, eval_str=True).parameters.items()
        }
    except (NameError, TypeError):
        return dict(given)
    return {name: _as_declared(declared.get(name), value) for name, value in given.items()}


def _as_declared(declared: object, value: object) -> object:
    shape = dataclass_in(declared)
    if shape is None:
        # JSON has one number: `speed=1.0` arrives as 1, and a parameter typed float alone takes 1.0.
        return float(value) if type(value) is int and _takes_a_float(declared) else value
    if not a_mapping(value):
        return value
    typed = typing.get_type_hints(shape)
    return shape(**{name: _as_declared(typed.get(name), given) for name, given in value.items()})


def _takes_a_float(declared: object) -> bool:
    options = typing.get_args(declared) or (declared,)
    return float in options and int not in options


def dataclass_in(declared: object) -> type | None:
    """The dataclass a declared type is, or holds in a union; None for any other."""
    if isinstance(declared, type) and dataclasses.is_dataclass(declared):
        return declared
    if isinstance(declared, types.UnionType):
        return next((one for one in typing.get_args(declared) if dataclass_in(one)), None)
    return None
