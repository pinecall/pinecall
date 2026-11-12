"""A screen: parts a page draws its own way, scenes the model moves, and what it reads of them."""

from dataclasses import dataclass

import pytest
from typing_extensions import override

from pinecall import Agent, DeclarationRefused, part, tool
from pinecall.screen import (
    NO_SCENE,
    SHOW_SCREEN,
    checked_scenes,
    draws_screen,
    scene_line,
    scenes_of,
    screen_of,
    showing_tool,
)

Agenda = part("agenda")
Slot = part("slot")


@dataclass(frozen=True)
class Hour:
    """An open hour."""

    at: str


def test_a_part_is_named_in_lowercase_since_the_page_maps_the_name() -> None:
    with pytest.raises(DeclarationRefused, match="lowercase"):
        part("Agenda")


def test_a_screen_is_its_parts_and_words_in_order_its_props_made_plain() -> None:
    drawn = [Agenda(Slot(at="9:00"), "o más tarde", day="lunes", first=Hour("9:00")), None, ""]
    assert screen_of(drawn) == [
        {
            "part": "agenda",
            "props": {"day": "lunes", "first": {"at": "9:00"}},
            "children": [{"part": "slot", "props": {"at": "9:00"}, "children": []}, "o más tarde"],
        }
    ]


def test_a_screen_of_something_no_page_draws_is_refused() -> None:
    with pytest.raises(DeclarationRefused, match="parts, words"):
        screen_of([object()])


def test_a_class_draws_a_screen_when_it_writes_its_own() -> None:
    class Plain(Agent):
        """Plain."""

    class Drawn(Agent):
        """Drawn."""

        @override
        def screen(self) -> object:
            """The agenda."""
            return Agenda()

    assert (draws_screen(Plain, Agent), draws_screen(Drawn, Agent)) == (False, True)


def test_scenes_are_named_in_lowercase_each_with_what_it_shows_and_none_is_taken() -> None:
    class Desk(Agent):
        """Desk."""

        scenes = {"agenda": "the open times you read"}  # noqa: RUF012 - the base's ClassVar

    class Wrong(Agent):
        """Wrong."""

        scenes = {NO_SCENE: "nothing"}  # noqa: RUF012 - the base's ClassVar

    assert scenes_of(Desk) == {"agenda": "the open times you read"}
    with pytest.raises(DeclarationRefused, match="named in lowercase"):
        scenes_of(Wrong)


def test_a_tool_that_shows_a_scene_the_class_lacks_is_refused() -> None:
    class Desk(Agent):
        """Desk."""

        @tool(shows="map")
        def find(self) -> str:
            """Finds it."""
            return "ok"

    with pytest.raises(DeclarationRefused, match="shows map, which is none of its scenes"):
        checked_scenes(Desk)


def test_the_screen_tool_offers_every_scene_and_none_and_asks_for_no_answer() -> None:
    spec = showing_tool({"agenda": "the open times"})
    assert spec.name == SHOW_SCREEN
    assert spec.parameters["properties"] == {
        "scene": {"type": "string", "enum": ["agenda", "none"]}
    }
    assert (spec.quiet, spec.side_effect) == (True, "read")


def test_the_model_reads_which_scene_is_up_and_a_class_with_none_reads_nothing() -> None:
    assert scene_line({}, None) == ""
    assert "shows no scene" in scene_line({"agenda": "times"}, None)
    assert "shows agenda (times)" in scene_line({"agenda": "times"}, "agenda")
