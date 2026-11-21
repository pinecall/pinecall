"""A call's state: its speech ids, the tools open, the events it receives, the app's declaration, opening and end."""

import asyncio

from runtime.agents.declaration import Declaration, ToolSpec
from runtime.calls.log.store import Store
from runtime.session.call import Call
from runtime.wire.commands import SessionConfigure, ToolsSet
from runtime.wire.declaration import AgentConfig as Declared
from runtime.wire.events import Custom
from runtime.wire.parts import ToolSpec as WiredTool
from tests.conftest import needs_the_database
from tests.session.conftest import Box, Through, context_of

A_TOOL = ToolSpec("book", "Book.", {"type": "object"})


@needs_the_database
async def test_speech_ids_are_numbered_from_one(box: Box, call: str) -> None:
    ongoing = Call(context_of(call), Declaration(slug="a"), box)
    assert (ongoing.speech(), ongoing.speech()) == ("sp_1", "sp_2")


@needs_the_database
async def test_everything_declared_is_open_until_a_tools_set_narrows_it(box: Box, store: Store, call: str) -> None:
    ongoing = Call(context_of(call), Declaration(slug="a", tools=(A_TOOL,)), box)
    ongoing.writing.open()
    assert ongoing.open_tools == {"book"}
    assert ongoing.list_closed_tools() == []
    undeclared = WiredTool(name="ghost", description="d", parameters={"type": "object"})
    await ongoing.set_tools(ToolsSet(tools=[undeclared]))
    assert ongoing.open_tools == frozenset()
    assert ongoing.list_closed_tools() == ["book"]
    await ongoing.writing.close(5)
    assert [entry.data for entry in await store.whole_of(call)] == [{"visible": []}]


@needs_the_database
async def test_an_event_from_a_widget_names_the_seat_it_came_from(box: Box, store: Store, call: str) -> None:
    config = Declaration(slug="a", events={"clicked": frozenset({"participant"})})
    ongoing = Call(context_of(call), config, box)
    ongoing.writing.open()
    await ongoing.receive("clicked", {"x": 1}, source="participant", identity="visitor_1")
    await ongoing.writing.close(5)
    (received,) = await store.whole_of(call)
    assert received.data == {
        "name": "clicked",
        "data": {"x": 1},
        "source": "participant",
        "identity": "visitor_1",
    }


@needs_the_database
async def test_a_configure_declares_for_this_call_and_sets_its_state(box: Box, store: Store, call: str) -> None:
    ongoing = Call(context_of(call), Declaration(slug="a"), box)
    ongoing.writing.open()
    await ongoing.configure(SessionConfigure(config=Declared(language="en-US"), state={"step": "greeted"}))
    await ongoing.writing.close(5)
    assert ongoing.declaration.language == "en-US"
    written = await store.whole_of(call)
    assert [(entry.type, entry.data.get("changed")) for entry in written] == [
        ("agent.configured", ["language"]),
        ("state.changed", ["step"]),
    ]


# The app's word after its end hook says the seal may go on: it comes after what the app wrote before it.
@needs_the_database
async def test_the_apps_end_hook_done_is_said_to_the_platform_after_its_lines_were_written(
    box: Box, store: Store, call: str
) -> None:
    written_then: list[list[str]] = []

    async def released() -> None:
        written_then.append([str(entry.data["name"]) for entry in await store.whole_of(call)])

    ending = Call(context_of(call), Declaration(slug="clinica-norte"), Through(box, releasing=released))
    ending.writing.open()
    ending.writing.write("custom", Custom(name="closed", data={}))
    await ending.app_finished()
    assert written_then == [["closed"]]
    await ending.writing.close(5)


async def test_a_call_whose_platform_waits_for_nothing_takes_the_apps_word_and_goes_on(box: Box) -> None:
    await Call(context_of("call_1"), Declaration(slug="clinica-norte"), box).app_finished()


# ── the app's opening ──


@needs_the_database
async def test_a_call_no_app_is_to_open_waits_for_nothing(box: Box, call: str) -> None:
    ongoing = Call(context_of(call), Declaration(slug="a"), box)
    assert await ongoing.wait_until_opened(0)
    assert ongoing.opened_after_s is None


@needs_the_database
async def test_a_call_its_app_is_to_open_is_opened_by_its_first_tools_set(box: Box, call: str) -> None:
    ongoing = Call(context_of(call), Declaration(slug="a", tools=(A_TOOL,)), box, awaits_app=True)
    ongoing.writing.open()
    waiting = asyncio.create_task(ongoing.wait_until_opened(5))
    await asyncio.sleep(0.05)
    assert not waiting.done()
    await ongoing.set_tools(ToolsSet(tools=[]))
    assert await waiting
    took = ongoing.opened_after_s
    assert took is not None and took >= 0.05
    # A second tools.set narrows the tools and opens nothing again: the distance is the first one's.
    await ongoing.set_tools(ToolsSet(tools=[]))
    assert ongoing.opened_after_s == took
    await ongoing.writing.close(5)


@needs_the_database
async def test_an_app_that_never_opens_holds_the_call_once_and_no_longer_than_it_may(box: Box, call: str) -> None:
    ongoing = Call(context_of(call), Declaration(slug="a"), box, awaits_app=True)
    assert not await ongoing.wait_until_opened(0.05)
    # Said once: the turns after the first wait for nothing.
    assert await ongoing.wait_until_opened(5)
    assert ongoing.opened_after_s is None


@needs_the_database
async def test_a_call_taken_up_again_waits_for_no_opening(box: Box, call: str) -> None:
    ongoing = Call(context_of(call), Declaration(slug="a"), box, awaits_app=True)
    ongoing.take_as_opened()
    assert await ongoing.wait_until_opened(0)
