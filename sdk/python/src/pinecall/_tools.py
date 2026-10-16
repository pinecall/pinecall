"""`@tool`: a method the model may call, what this state shows of them, and running one."""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, TypedDict, TypeVar, overload

from pydantic import BaseModel
from typing_extensions import Unpack

from pinecall import _running, _spec
from pinecall.errors import DeclarationRefused
from pinecall.wire.parts import ToolSpec

_F = TypeVar("_F", bound=Callable[..., object])

# Where `@tool` leaves its options on the function, for the class to read when it is created.
MARK = "__pinecall_tool__"


class ToolOptions(TypedDict, total=False):
    """What `@tool(...)` takes."""

    stage: str | Sequence[str]
    when: Callable[[Any], object]
    confirm: str
    announce: str
    preview: int
    pii: Sequence[str]
    timeout: float


@overload
def tool(method: _F, /) -> _F: ...
@overload
def tool(**options: Unpack[ToolOptions]) -> Callable[[_F], _F]: ...
def tool(method: _F | None = None, /, **options: Unpack[ToolOptions]) -> _F | Callable[[_F], _F]:
    """Make a method a tool the model may call; its docstring is what the model reads.

    ```python
    @tool(stage="book", confirm="Reservado: {{result.when}}.")
    def book(self, slot: str) -> dict:
        \"\"\"Books the hour the caller just confirmed.\"\"\"
    ```

    A parameter's description is what the method's own `Args:` section says of it.

    Args:
        method: the method, when `@tool` is written with no options.
        stage: the stage, or the stages, in which the model sees the tool.
        when: a test of the agent's state; the model sees the tool while it holds.
        confirm: what is read back to the caller before the tool runs, which makes it
            irreversible; `{{result.x}}` names a field of what it returns.
        preview: how many rows of a list the model sees; the state keeps every one.
        pii: the parameters that carry personal data, masked in the log.
        timeout: how many seconds the platform waits for the method.
    """
    unknown = set(options) - set(ToolOptions.__annotations__)
    if unknown:
        raise DeclarationRefused(f"@tool takes no {', '.join(sorted(unknown))}")

    def marked(function: _F) -> _F:
        setattr(function, MARK, options)
        return function

    return marked if method is None else marked(method)


@dataclass(frozen=True)
class Declared:
    """One tool as the class declared it: its options, its spec, and its arguments' model."""

    name: str
    stages: tuple[str, ...] | None
    when: Callable[[Any], object] | None
    preview: int | None
    spec: ToolSpec
    arguments: type[BaseModel]


def declared_tools(
    cls: type, base: type, inherited: Mapping[str, Declared], stages: tuple[str, ...] | None
) -> dict[str, Declared]:
    """The class's tools, its parents' first: a method marked by `@tool`, read once."""
    declared = dict(inherited)
    for name, value in vars(cls).items():
        options: ToolOptions | None = getattr(value, MARK, None)
        if options is None:
            # A method that overrides a parent's tool without `@tool` is no longer one.
            declared.pop(name, None)
            continue
        if hasattr(base, name):
            raise DeclarationRefused(
                f"tool {name}: a tool named so would hide the agent's own {name}"
            )
        declared[name] = declaring(cls, name, value, options, stages)
    return declared


def declaring(
    cls: type,
    name: str,
    method: Callable[..., object],
    options: ToolOptions,
    stages: tuple[str, ...] | None,
) -> Declared:
    """Check one tool's declaration against its class, and build what the gateway receives."""
    wanted = stages_named(cls, name, options.get("stage"), stages)
    pii = options.get("pii")
    arguments = _spec.arguments_model(name, method)
    said: dict[str, object] = {
        "confirm": options.get("confirm"),
        "announce": options.get("announce"),
        "pii": None if pii is None else tuple(pii),
        "timeout": options.get("timeout"),
    }
    spec = _spec.spec_of(name, method, arguments, said)
    return Declared(name, wanted, options.get("when"), options.get("preview"), spec, arguments)


def stages_named(
    cls: type, name: str, stage: str | Sequence[str] | None, stages: tuple[str, ...] | None
) -> tuple[str, ...] | None:
    """The stages a tool names, refused when the class declares no stage or not these."""
    if stage is None:
        return None
    wanted = (stage,) if isinstance(stage, str) else tuple(stage)
    if stages is None:
        raise DeclarationRefused(
            f"tool {name}: stage names a value of this agent's own stage field, and "
            f'{cls.__name__} declares none; add stage: Literal["identify", "book"] to the class, '
            "or ask when= instead"
        )
    unknown = [one for one in wanted if one not in stages]
    if unknown:
        raise DeclarationRefused(
            f"tool {name}: {', '.join(unknown)} is not one of this agent's stages"
            f" ({', '.join(stages)})"
        )
    return wanted


def shows(declared: Declared, agent: object) -> bool:
    """Whether the model sees the tool in the agent's state now: its stage, then its `when`."""
    if declared.stages is not None and getattr(agent, "stage", None) not in declared.stages:
        return False
    return declared.when is None or bool(declared.when(agent))


def ran(agent: object, declared: Declared, given: Mapping[str, object]) -> object:
    """Run the tool to its end, its writes authored by its name, its answer cut to its preview."""
    arguments = _spec.validated(declared.name, declared.arguments, given)
    return previewed(
        _running.called(declared.name, getattr(agent, declared.name), **arguments), declared
    )


async def run(agent: object, declared: Declared, given: Mapping[str, object]) -> object:
    """The same, from a loop: an `async def` on it, a `def` on a thread."""
    arguments = _spec.validated(declared.name, declared.arguments, given)
    return previewed(
        await _running.run(declared.name, getattr(agent, declared.name), **arguments), declared
    )


def previewed(result: object, declared: Declared) -> object:
    """Cut a list to the rows the model sees; what the state kept is untouched."""
    if declared.preview is None or not isinstance(result, list):
        return result
    rows: list[object] = result  # pyright: ignore[reportUnknownVariableType]
    return rows[: declared.preview]
