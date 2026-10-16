"""Listeners: by type and for every event, stopped on request, one failing never stopping others."""

import asyncio

from pinecall._listeners import Listeners
from pinecall.wire.commands import Ping
from pinecall.wire.frames import WireModel


def test_a_listener_hears_its_type_until_it_stops_and_an_every_event_one_hears_all() -> None:
    listeners: Listeners[str] = Listeners(lambda error: None)
    heard: list[str] = []
    stop = listeners.on("pong", lambda event, where: heard.append(f"pong@{where}"))
    listeners.on_any(lambda type_, event, where: heard.append(f"any:{type_}"))
    listeners.emit("pong", Ping(), "CA_1")
    stop()
    listeners.emit("pong", Ping(), "CA_1")
    listeners.emit("custom", Ping(), "CA_1")
    assert heard == ["pong@CA_1", "any:pong", "any:pong", "any:custom"]


def test_a_listener_that_raises_is_said_and_the_next_one_still_hears() -> None:
    said: list[Exception] = []
    listeners: Listeners[None] = Listeners(said.append)
    heard: list[str] = []

    def broken(event: WireModel, where: None) -> None:
        raise ValueError("mine")

    listeners.on("pong", broken)
    listeners.on("pong", lambda event, where: heard.append("still"))
    listeners.emit("pong", Ping(), None)
    assert ([str(error) for error in said], heard) == (["mine"], ["still"])


def test_an_async_listener_runs_on_the_loop_and_its_failure_is_said() -> None:
    said: list[Exception] = []

    async def broken(event: WireModel, where: None) -> None:
        await asyncio.sleep(0)
        raise ValueError("later")

    async def heard() -> None:
        listeners: Listeners[None] = Listeners(said.append)
        listeners.on("pong", broken)
        listeners.emit("pong", Ping(), None)
        await asyncio.sleep(0.01)

    asyncio.run(heard())
    assert [str(error) for error in said] == ["later"]
