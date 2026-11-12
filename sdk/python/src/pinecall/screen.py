"""A screen: what an agent puts on its caller's page, as named parts the page draws its own way."""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import cast

from pydantic import TypeAdapter

from pinecall import _tools
from pinecall.errors import DeclarationRefused
from pinecall.wire._names import JsonObject
from pinecall.wire.parts import ToolSpec

SCREEN = "screen"
"""The field of a call's state its screen travels in, public to the caller's own page."""

TASK_GIVE = "task.give"
"""The event a page answers a task with: `{"task": "phone", "given": {"number": "…"}}`."""

SHOW_SCREEN = "show_screen"
"""The tool the model moves the caller's screen with, offered to a class that declares scenes."""

NO_SCENE = "none"
"""The scene that takes what a tool put up away: the screen with nothing chosen."""

A_PART = re.compile(r"^[a-z][a-z0-9-]*$")
A_SCENE = re.compile(r"^[a-z][a-z0-9_-]*$")

# What crosses to a browser is JSON: dataclasses, models and dates are made plain.
PLAIN: TypeAdapter[object] = TypeAdapter(object)

ScreenItem = Mapping[str, object] | str
"""One part of a screen as the page reads it (`{part, props, children}`), or words between."""


@dataclass(frozen=True)
class Shown:
    """One part with what it was given and what it holds, as `screen()` returns it."""

    part: str
    props: Mapping[str, object]
    children: Sequence["Shown | str"] = field(default_factory=tuple["Shown | str", ...])


@dataclass(frozen=True)
class Part:
    """A part of the agent's own: `Agenda = part("agenda")`, used as `Agenda(slots=slots)`."""

    name: str

    def __call__(self, *children: "Shown | str", **props: object) -> Shown:
        """This part with these props, holding these children."""
        return Shown(self.name, props, children)


def part(name: str) -> Part:
    """Declare a part: the name is what the page maps to a component of its own.

    ```python
    Agenda = part("agenda")

    def screen(self):
        return [Agenda(slots=self.slots)]
    ```

    Args:
        name: lowercase letters, digits and dashes.
    """
    if not A_PART.match(name):
        raise DeclarationRefused(
            f'a part\'s name is lowercase letters, digits and dashes, and "{name}" is not:'
            " it is what the page maps to its component"
        )
    return Part(name)


def screen_of(drawn: object) -> list[ScreenItem]:
    """What `screen()` returned, as the parts a page reads."""
    if drawn is None or isinstance(drawn, bool):
        return []
    if isinstance(drawn, str):
        return [drawn.strip()] if drawn.strip() else []
    if isinstance(drawn, int | float):
        return [str(drawn)]
    if isinstance(drawn, Shown):
        props: JsonObject = PLAIN.dump_python(dict(drawn.props), mode="json")
        return [{"part": drawn.part, "props": props, "children": screen_of(list(drawn.children))}]
    if isinstance(drawn, Sequence):
        listed = cast("Sequence[object]", drawn)
        return [item for one in listed for item in screen_of(one)]
    raise DeclarationRefused(
        f"a screen is parts, words and lists of them, and {type(drawn).__name__} is none"
    )


def draws_screen(cls: type, base: type) -> bool:
    """Whether the class draws a screen of its own."""
    return getattr(cls, "screen", None) is not getattr(base, "screen", None)


def scenes_of(cls: type) -> dict[str, str]:
    """The scenes a class declares, each with what it shows; empty for a class with none."""
    declared: object = getattr(cls, "scenes", {})
    if not isinstance(declared, Mapping):
        raise DeclarationRefused(
            f"{cls.__name__}: scenes names each scene with what it shows:"
            ' {"agenda": "the open times you last read"}'
        )
    scenes: dict[str, str] = {}
    for name, what in declared.items():  # pyright: ignore[reportUnknownVariableType]
        if not isinstance(name, str) or not A_SCENE.match(name) or name == NO_SCENE:
            raise DeclarationRefused(
                f'{cls.__name__}: a scene is named in lowercase, and not "{NO_SCENE}":'
                f' "{name}" is not one'
            )
        if not isinstance(what, str) or not what.strip():
            raise DeclarationRefused(
                f"{cls.__name__}: the scene {name} says what it shows, in words"
            )
        scenes[name] = what
    return scenes


def checked_scenes(cls: type) -> dict[str, str]:
    """The class's scenes, every tool's `shows` held to one of them."""
    scenes = scenes_of(cls)
    declared: dict[str, _tools.Declared] = getattr(cls, "_pinecall_tools", {})
    for tool in declared.values():
        if tool.shows is not None and tool.shows not in scenes:
            raise DeclarationRefused(
                f"{cls.__name__}.{tool.name} shows {tool.shows}, which is none of its scenes"
            )
    return scenes


def showing_tool(scenes: Mapping[str, str]) -> ToolSpec:
    """The tool the model moves the screen with: one of the scenes, or `none`."""
    listed = "; ".join(f"{name}: {what}" for name, what in scenes.items())
    return ToolSpec(
        name=SHOW_SCREEN,
        description=(
            "Put a scene on the caller's screen, or keep the one there, in the same turn as your"
            f" words. {listed}; {NO_SCENE}: nothing chosen."
        ),
        parameters={
            "type": "object",
            "properties": {"scene": {"type": "string", "enum": [*scenes, NO_SCENE]}},
            "required": ["scene"],
        },
        side_effect="read",
        quiet=True,
    )


def scene_line(scenes: Mapping[str, str], scene: str | None) -> str:
    """What the model reads of the screen in this turn; empty for a class with no scenes."""
    if not scenes:
        return ""
    if scene is None:
        return (
            f"The caller's screen shows no scene. Put one up with {SHOW_SCREEN} when it helps them."
        )
    return (
        f"The caller's screen shows {scene} ({scenes.get(scene, scene)}). It goes away when you"
        f" answer about something else; call {SHOW_SCREEN} to keep it or to show another."
    )
