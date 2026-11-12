"""A call's screen as the bridge keeps it: drawn, declared public, and moved by the turns."""

from typing_extensions import override

from pinecall import Agent, CallLine, CallWorld, part
from pinecall._screened import (
    Screened,
    redrawn,
    scene_chosen,
    screen_declared,
    screens,
    state_with,
    turned,
    unscreened,
)

Agenda = part("agenda")


class Desk(Agent):
    """Desk."""

    scenes = {"agenda": "the open times"}  # noqa: RUF012 - the base's ClassVar

    @override
    def screen(self) -> object:
        """The agenda of the day."""
        return Agenda(day="lunes")


def world() -> CallWorld:
    return CallWorld(CallLine(id="CA_1", contact="web_1", channel="web"))


def test_a_class_with_a_screen_declares_its_field_public_and_with_tasks_the_pages_event() -> None:
    assert screens([Desk], Agent)
    declared = screen_declared({"events": [{"name": "paid", "from": ["app"]}]}, tasks=True)
    assert declared["state_fields"] == [{"name": "screen", "visibility": "public"}]
    assert declared["events"] == [
        {"name": "paid", "from": ["app"]},
        {"name": "task.give", "from": ["participant"]},
    ]


def test_a_screen_is_sent_when_it_moved_and_rides_the_state_but_never_comes_back_into_it() -> None:
    screened = Screened()
    assert redrawn(Desk().screen(), None, screened)
    assert not redrawn(Desk().screen(), None, screened)
    state = state_with({"day": "lunes"}, screened)
    assert state["screen"] == [{"part": "agenda", "props": {"day": "lunes"}, "children": []}]
    assert unscreened(state) == {"day": "lunes"}


def test_the_model_puts_a_scene_up_or_takes_it_down_and_one_it_lacks_is_said() -> None:
    call, screened = world(), Screened()
    assert scene_chosen(call, screened, Desk, "agenda") == "shown"
    assert (call.scene, screened.kept) == ("agenda", True)
    assert scene_chosen(call, screened, Desk, "map").startswith("There is no scene map")
    scene_chosen(call, screened, Desk, "none")
    assert call.scene is None


def test_a_turn_of_the_caller_that_kept_no_scene_takes_it_away_once_the_agent_waits() -> None:
    call, screened = world(), Screened()
    call.scene = "agenda"
    assert not turned("turn.user", call, screened)
    assert turned("agent.waiting", call, screened)
    assert call.scene is None
    call.scene = "agenda"
    turned("turn.user", call, screened)
    screened.kept = True
    assert not turned("agent.waiting", call, screened)
    assert call.scene == "agenda"
