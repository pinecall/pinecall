"""One agent on the socket: a tool call answered once, a console's ask, listeners, its calls."""

import asyncio
from typing import cast

import pytest

from pinecall import DevRefused
from pinecall._agent_socket import Tool
from pinecall._calls import Call
from pinecall._connection import Backoff
from pinecall.client import Client
from pinecall.wire._names import JsonObject
from pinecall.wire.frames import WireModel
from pinecall.wire.parts import AgentConfig, DevVerb, ToolSpec
from tests.fakes.gateway import KEY, FakeGateway


def spec(name: str) -> ToolSpec:
    return ToolSpec(name=name, description=f"{name}.", parameters={"type": "object"})


async def find(arguments: JsonObject, call: Call) -> JsonObject:
    return {"found": arguments["name"], "call": call.id}


def fails(arguments: JsonObject, call: Call) -> None:
    raise ValueError("la agenda no contesta")


async def connected(gateway: FakeGateway) -> Client:
    client = Client(gateway.url, KEY, backoff=Backoff(first_s=0.01))
    client.agent("clinica", tools=[Tool(spec("find_patient"), find), Tool(spec("book"), fails)])
    await client.connect()
    return client


def data_of(gateway: FakeGateway, type_: str) -> list[dict[str, object]]:
    return [cast("dict[str, object]", one["data"]) for one in gateway.commands_of(type_)]


async def results(gateway: FakeGateway, count: int) -> list[dict[str, object]]:
    await gateway.until(lambda: len(gateway.commands_of("tool.result")) == count)
    return data_of(gateway, "tool.result")


async def test_a_tool_call_gets_exactly_one_result_with_its_output_and_how_long_it_took(
    gateway: FakeGateway,
) -> None:
    client = await connected(gateway)
    asked = {"call_id": "tc_1", "name": "find_patient", "arguments": {"name": "Ana"}}
    await gateway.emit("clinica", "CA_1", "tool.call", asked)
    [answer] = await results(gateway, 1)
    assert answer == {
        "call_id": "tc_1",
        "name": "find_patient",
        "output": {"found": "Ana", "call": "CA_1"},
        "duration_s": pytest.approx(0, abs=0.5),
    }
    await client.close()


async def test_a_tool_that_raises_or_one_nobody_declared_still_gets_one_result(
    gateway: FakeGateway,
) -> None:
    client = await connected(gateway)
    await gateway.emit(
        "clinica", "CA_1", "tool.call", {"call_id": "tc_1", "name": "book", "arguments": {}}
    )
    await gateway.emit(
        "clinica", "CA_1", "tool.call", {"call_id": "tc_2", "name": "pay", "arguments": {}}
    )
    answers = await results(gateway, 2)
    assert answers[0]["error"] == "la agenda no contesta"
    assert answers[1] == {
        "call_id": "tc_2",
        "name": "pay",
        "error": "this app declares no tool called pay",
    }
    await client.close()


async def test_a_consoles_ask_is_answered_by_the_handler_refused_with_its_status_or_501(
    gateway: FakeGateway,
) -> None:
    client = await connected(gateway)
    held = client.agent("otro")
    await held.open()

    def handler(verb: DevVerb, data: JsonObject) -> JsonObject:
        if verb == "view.render":
            return {"name": "Ficha", "nodes": []}
        raise DevRefused(404, "this process answers only view.render")

    held.on_dev(handler)
    for id_, verb in (("d1", "view.render"), ("d2", "goldens.roster")):
        await gateway.emit("otro", None, "dev.request", {"id": id_, "verb": verb, "data": {}})
    await gateway.emit(
        "clinica", None, "dev.request", {"id": "d3", "verb": "view.render", "data": {}}
    )
    await gateway.until(lambda: len(gateway.commands_of("dev.answer")) == 3)
    answers = {one["id"]: one for one in data_of(gateway, "dev.answer")}
    assert answers["d1"] == {"id": "d1", "result": {"name": "Ficha", "nodes": []}}
    assert answers["d2"]["refused"] == {
        "status": 404,
        "detail": "this process answers only view.render",
    }
    assert cast("dict[str, object]", answers["d3"]["refused"])["status"] == 501
    await client.close()


async def test_listeners_hear_an_event_with_its_call_and_one_that_raises_is_said(
    gateway: FakeGateway,
) -> None:
    client = await connected(gateway)
    held = client.agent("clinica")
    heard: list[tuple[str, str | None]] = []
    said: list[Exception] = []
    client.on_errors(said.append)

    def turn(event: WireModel, call: Call | None) -> None:
        heard.append((type(event).__name__, None if call is None else call.id))

    def broken(event: WireModel, call: Call | None) -> None:
        raise RuntimeError("a listener of mine")

    held.on("custom", turn)
    held.on("custom", broken)
    await gateway.emit("clinica", "CA_1", "custom", {"name": "x", "data": {}})
    await gateway.until(lambda: heard == [("Custom", "CA_1")])
    assert str(said[0]) == "a listener of mine"
    await client.close()


async def test_a_call_is_held_from_its_first_entry_and_let_go_once_it_ends(
    gateway: FakeGateway,
) -> None:
    client = await connected(gateway)
    held = client.agent("clinica")
    await gateway.emit("clinica", "CA_1", "custom", {"name": "x", "data": {}})
    await gateway.until(lambda: [call.id for call in held.calls.live] == ["CA_1"])
    ended = {"reason": "caller_hung_up", "ended_by": "caller", "ended_at": 1.0, "duration_s": 2.0}
    await gateway.emit("clinica", "CA_1", "call.ended", ended)
    await gateway.until(lambda: held.calls.live == [])
    await client.close()


async def test_configuring_sends_the_declaration_with_the_fields_changed(
    gateway: FakeGateway,
) -> None:
    client = Client(gateway.url, KEY)
    held = client.agent("clinica", AgentConfig(uses_knowledge=True))
    await client.connect()
    changed = await held.configure({"uses_knowledge": False})
    assert changed.changed == ["tools", "uses_knowledge"]
    assert gateway.commands_of("agent.configure")[-1]["data"] == {
        "config": {"uses_knowledge": False, "tools": []}
    }
    await asyncio.sleep(0)
    await client.close()
