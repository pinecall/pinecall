"""What the bridge sends: only the tools shown now, the state as JSON with its screen."""

from pinecall import Agent, CallLine, CallWorld, GetEmail
from pinecall._asking import Asking
from pinecall._calls import Call
from pinecall._live import Live
from pinecall._screened import Screened
from pinecall._sending import as_object, jsonable, state_of, visible_tools
from pinecall.call import nowhere


class Desk(Agent):
    """Desk."""

    scenes = {"agenda": "the open times"}  # noqa: RUF012 - the base's ClassVar


def served(asking: Asking) -> Live:
    call = Call("CA_1", nowhere, 0.0, nowhere)
    world = CallWorld(CallLine(id="CA_1", contact="web_1", channel="web"))
    return Live(Desk().serving(world), Desk, world, call, asking)


def test_the_model_sees_every_tool_shown_now_and_the_screen_tool_of_its_scenes() -> None:
    assert [spec.name for spec in visible_tools(served(Asking([])))] == ["show_screen"]


async def test_while_a_tool_waits_for_an_answer_only_the_tool_that_gives_it_is_open() -> None:
    asking = Asking([GetEmail])

    async def booking() -> object:
        return await asking.ask(GetEmail)

    await asking.run("book", booking)
    assert [spec.name for spec in visible_tools(served(asking))] == ["give_email"]


def test_the_state_carries_the_screen_once_drawn() -> None:
    held = served(Asking([]))
    assert "screen" not in state_of(held)
    held.screened = Screened(["listo"], '["listo"]')
    assert state_of(held)["screen"] == ["listo"]


def test_a_value_is_made_json_and_a_logged_value_an_object() -> None:
    assert jsonable({"at": (1, 2)}) == {"at": [1, 2]}
    assert (as_object(None), as_object(3), as_object({"a": 1})) == ({}, {"value": 3}, {"a": 1})
