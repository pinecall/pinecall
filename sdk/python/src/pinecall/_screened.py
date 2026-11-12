"""A call's screen as the bridge keeps it: drawn from the agent, sent in the state when it moved."""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from pinecall.call import CallWorld
from pinecall.errors import DeclarationRefused
from pinecall.screen import (
    NO_SCENE,
    SCREEN,
    SHOW_SCREEN,
    TASK_GIVE,
    ScreenItem,
    checked_scenes,
    draws_screen,
    scenes_of,
    screen_of,
    showing_tool,
)
from pinecall.wire.parts import ToolSpec

EMPTY = "[]"


@dataclass
class Screened:
    """The screen a call's page was last sent, and whether this turn kept its scene."""

    screen: list[ScreenItem] | None = None
    key: str = EMPTY
    by_user: bool = False
    kept: bool = False


def screens(classes: Sequence[type], base: type) -> bool:
    """Whether one of the classes draws a screen: its field is then public."""
    return any(draws_screen(one, base) for one in classes)


def screen_declared(declared: dict[str, object], *, tasks: bool) -> dict[str, object]:
    """A class with a screen declares its field public, and with tasks the page's event."""
    fields = [*_listed(declared.get("state_fields")), {"name": SCREEN, "visibility": "public"}]
    added: dict[str, object] = {**declared, "state_fields": fields}
    if tasks:
        added["events"] = [
            *_listed(declared.get("events")),
            {"name": TASK_GIVE, "from": ["participant"]},
        ]
    return added


def _listed(given: object) -> list[object]:
    return list(given) if isinstance(given, list) else []  # pyright: ignore[reportUnknownArgumentType]


def redrawn(drawn: object, shown: object, screened: Screened) -> bool:
    """Draw the screen with what is shown over it; True when it is not the one already sent."""
    screen = screen_of([drawn, shown])
    key = json.dumps(screen, sort_keys=True)
    if key == screened.key:
        return False
    screened.screen, screened.key = screen, key
    return True


def state_with(snapshot: Mapping[str, object], screened: Screened) -> dict[str, object]:
    """The call's state as the gateway is told it: the agent's own, and its screen once drawn."""
    return dict(snapshot) if screened.screen is None else {**snapshot, SCREEN: screened.screen}


def unscreened(state: Mapping[str, object]) -> dict[str, object]:
    """A state the gateway kept, without the screen: it is drawn again, never restored."""
    return {name: value for name, value in state.items() if name != SCREEN}


def scene_tools(classes: Sequence[type], taken: Sequence[str]) -> list[ToolSpec]:
    """The tool the classes of a call move their screen with, declared once for all of them."""
    scenes: dict[str, str] = {}
    for one in classes:
        scenes |= checked_scenes(one)
    if not scenes:
        return []
    if SHOW_SCREEN in taken:
        raise DeclarationRefused(
            f"{SHOW_SCREEN} is the tool a screen is moved with,"
            " and an agent declares a tool so named"
        )
    return [showing_tool(scenes)]


def scene_tool_of(cls: type) -> list[ToolSpec]:
    """The tool the class serving the call moves its screen with, when it declares scenes."""
    scenes = scenes_of(cls)
    return [showing_tool(scenes)] if scenes else []


def scene_chosen(world: CallWorld, screened: Screened, cls: type, scene: object) -> str:
    """The model chose a scene, or none: it is the call's now, and kept through this turn."""
    scenes = scenes_of(cls)
    if scene != NO_SCENE and scene not in scenes:
        return f"There is no scene {scene}: {', '.join([*scenes, NO_SCENE])}."
    world.scene = None if scene == NO_SCENE else str(scene)
    screened.kept = True
    return "shown"


def turned(kind: str, world: CallWorld, screened: Screened) -> bool:
    """A turn went by; one the caller opened that kept no scene takes it away. True when it moved.

    Read at `agent.waiting`, once every sentence and tool of the answer is done.
    """
    if kind == "turn.user":
        screened.by_user, screened.kept = True, False
        return False
    if kind != "agent.waiting" or not screened.by_user:
        return False
    screened.by_user = False
    if screened.kept or world.scene is None:
        return False
    world.scene = None
    return True
