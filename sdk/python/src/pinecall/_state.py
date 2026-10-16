"""The state a class declares: its fields, the stage, the writes, and who made each one."""

import inspect
import sys
import time
import typing
from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Literal, TypeVar, overload

from pinecall import _author
from pinecall.errors import DeclarationRefused, NotAStage, UnauthoredWrite
from pinecall.wire.parts import StateFieldSpec, Visibility

_T = TypeVar("_T")

STAGE = "stage"

# Where `Agent` keeps what its class declares, read here by name since `agent.py` imports this;
# and where an instance keeps its state. Opened on first use, so a subclass's own `__init__`
# needs no `super().__init__()`.
FIELDS = "_pinecall_fields"
STORE = "_pinecall_state"


@dataclass(frozen=True)
class Change:
    """One recorded write: which field, what it held before and after, who wrote it, when."""

    seq: int
    field: str
    before: object
    after: object
    author: str
    at: float


@dataclass(frozen=True)
class Declared:
    """What `state(...)` says about one field: its opening value and who may see it."""

    default: object = None
    visibility: Visibility | None = None


@overload
def state(*, pii: bool = False, visibility: Visibility | None = None) -> None: ...
@overload
def state(default: _T, *, pii: bool = False, visibility: Visibility | None = None) -> _T: ...
def state(
    default: object = None, *, pii: bool = False, visibility: Visibility | None = None
) -> object:
    """Declare a field that needs more than a default: who may see it.

    Every annotated, public, non-`ClassVar` attribute of an agent is already a state field; this
    is for the one that also says its visibility.

    Args:
        default: the value the field opens every call with; each call gets its own copy.
        pii: the field holds personal data; the same as `visibility="pii"`.
        visibility: `"public"`, `"tenant"` or `"pii"`; left out, the wire's default (`tenant`).
    """
    if pii and visibility not in (None, "pii"):
        raise DeclarationRefused(f"a field is pii or {visibility}, not both")
    return Declared(default, "pii" if pii else visibility)


@dataclass(frozen=True)
class Fields:
    """Everything a class declares about its state, read once when the class is created."""

    declared: Mapping[str, Declared]
    derived: tuple[str, ...]
    stages: tuple[str, ...] | None


@dataclass
class Store:
    """One instance's state, and what it recorded since it was sealed."""

    values: dict[str, object]
    changes: list[Change] = field(default_factory=list[Change])
    listeners: list[Callable[[Change], None]] = field(
        default_factory=list[Callable[[Change], None]]
    )
    seq: int = 0
    sealed: bool = False

    def next_seq(self) -> int:
        """The next number in this instance's own order of things."""
        self.seq += 1
        return self.seq


class Field:
    """The descriptor a declared field becomes: reading is the store's, writing is recorded."""

    def __init__(self, name: str) -> None:
        """Stand for the field `name`."""
        self.name = name

    def __get__(self, agent: object, owner: type | None = None) -> object:
        """The field's value on `agent`, or the descriptor itself on the class."""
        if agent is None:
            return self
        return store_of(agent).values[self.name]

    def __set__(self, agent: object, value: object) -> None:
        """Write the field, recording who wrote it once the agent is sealed."""
        write(agent, self.name, value)


def store_of(agent: object) -> Store:
    """The agent's store, opened at each field's first value the first time it is asked for."""
    kept = vars(agent)
    store = kept.get(STORE)
    if not isinstance(store, Store):
        fields: Fields = getattr(type(agent), FIELDS)
        # Copied, so no two calls ever share one list.
        store = Store({name: deepcopy(said.default) for name, said in fields.declared.items()})
        kept[STORE] = store
    return store


def write(agent: object, name: str, value: object) -> None:
    """Every write of a field goes through here: refused unauthored once sealed, recorded if new."""
    store = store_of(agent)
    fields: Fields = getattr(type(agent), FIELDS)
    stages = fields.stages
    if name == STAGE and stages is not None and value is not None and value not in stages:
        raise NotAStage(f"stage is one of {', '.join(stages)}, not {value!r}")
    if not store.sealed:
        store.values[name] = value
        return
    author = _author.current()
    if author is None:
        raise UnauthoredWrite(name)
    before = store.values[name]
    store.values[name] = value
    # An equal value is not a change: nothing to render again, nothing to log.
    if before == value:
        return
    change = Change(store.next_seq(), name, before, value, author, time.time())
    store.changes.append(change)
    for listener in list(store.listeners):
        listener(change)


def collapsed(store: Store, summary: str) -> None:
    """Replace the recorded changes with one summary; the state itself is untouched."""
    store.changes.clear()
    store.changes.append(
        Change(store.next_seq(), "@summary", None, summary, "collapse", time.time())
    )


def fields_of(cls: type, base: type, inherited: Fields | None) -> Fields:
    """Read the class's own annotations into fields, over what its parent already declared."""
    declared = dict(inherited.declared) if inherited is not None else {}
    stages = inherited.stages if inherited is not None else None
    for name, annotation in own_annotations(cls).items():
        if name.startswith("_") or is_class_var(annotation):
            continue
        if hasattr(base, name):
            raise DeclarationRefused(
                f"{cls.__name__}.{name}: `{name}` is a name the agent itself uses;"
                " call the field otherwise"
            )
        said = vars(cls).get(name)
        if callable(said) or isinstance(said, property):
            raise DeclarationRefused(
                f"{cls.__name__}.{name} is annotated as a field and defined as more"
            )
        if name == STAGE:
            stages = stages_in(cls, annotation)
            if said is None:
                said = stages[0]
        declared[name] = said if isinstance(said, Declared) else Declared(said)
        setattr(cls, name, Field(name))
    if stages is not None and declared[STAGE].default not in stages:
        raise DeclarationRefused(f"{cls.__name__}: the stage opens at one of {', '.join(stages)}")
    return Fields(declared, derived_of(cls, base, declared), stages)


def own_annotations(cls: type) -> dict[str, object]:
    """The annotations written in the class's own body, unevaluated where they were strings."""
    if sys.version_info >= (3, 14):
        import annotationlib  # noqa: PLC0415 - 3.14 evaluates annotations lazily; this reads them unevaluated

        return dict(annotationlib.get_annotations(cls, format=annotationlib.Format.FORWARDREF))
    return dict(inspect.get_annotations(cls))


def is_class_var(annotation: object) -> bool:
    """Whether an annotation, written or as a string, says `ClassVar`."""
    if isinstance(annotation, str):
        return annotation.startswith(("ClassVar", "typing.ClassVar"))
    return annotation is typing.ClassVar or typing.get_origin(annotation) is typing.ClassVar


def stages_in(cls: type, annotation: object) -> tuple[str, ...]:
    """The values a `stage: Literal[...]` annotation names, in the order written."""
    if isinstance(annotation, str):
        scope = {**vars(sys.modules[cls.__module__]), "Literal": Literal}
        annotation = eval(annotation, scope)  # noqa: S307 - the class's own annotation, in its own module
    values = typing.get_args(annotation) if typing.get_origin(annotation) is Literal else ()
    if not values or not all(isinstance(value, str) for value in values):
        raise DeclarationRefused(
            f'{cls.__name__}.stage names the values it may hold: stage: Literal["identify", "book"]'
        )
    return tuple(str(value) for value in values)


def derived_of(cls: type, base: type, declared: Mapping[str, Declared]) -> tuple[str, ...]:
    """The public properties of the class and its parents: derived fields, in every snapshot."""
    found: dict[str, None] = {}
    for step in reversed(cls.__mro__):
        if not issubclass(step, base) or step is base:
            continue
        for name, value in vars(step).items():
            if isinstance(value, property) and not name.startswith("_") and name not in declared:
                found[name] = None
    return tuple(found)


def visibilities_of(fields: Fields) -> list[StateFieldSpec]:
    """The fields that said who may see them, as `agent.configure` carries them."""
    return [
        StateFieldSpec(name=name, visibility=said.visibility)
        for name, said in fields.declared.items()
        if said.visibility is not None
    ]
