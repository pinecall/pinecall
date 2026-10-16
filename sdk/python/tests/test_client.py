"""The client against a gateway on 127.0.0.1: registering, refusals, a drop, a drain, a search."""

import asyncio

import pytest

from pinecall import NotConnected, Refused, WireError
from pinecall._agent_socket import Tool
from pinecall._calls import Call
from pinecall._connection import Backoff
from pinecall.client import Client, Drained
from pinecall.wire._names import JsonObject
from pinecall.wire.commands import Ping
from pinecall.wire.frames import Entry
from pinecall.wire.parts import AgentConfig, ToolSpec
from tests.fakes.gateway import KEY, FakeGateway

QUICK = Backoff(first_s=0.01, cap_s=0.05)


def client_of(gateway: FakeGateway, key: str = KEY) -> Client:
    return Client(gateway.url, key, "sandbox", backoff=QUICK)


async def test_connecting_registers_each_agent_and_then_declares_it(gateway: FakeGateway) -> None:
    client = client_of(gateway)
    held = client.agent("clinica-norte", AgentConfig(uses_knowledge=True))
    await client.connect()
    assert [one["type"] for one in gateway.received] == ["agent.register", "agent.configure"]
    registered = gateway.commands_of("agent.register")[0]
    assert registered["id"] == "clinica-norte:agent.register"
    assert registered["data"] == {
        "routes": [],
        "sdk": client.sdk,
        "host": client.host,
        "takes_unclaimed": True,
    }
    assert gateway.commands_of("agent.configure")[0]["data"] == {
        "config": {"uses_knowledge": True, "tools": []}
    }
    assert held.app == "app_1"
    await client.close()


async def test_the_key_and_the_world_travel_as_headers_and_never_in_the_url(
    gateway: FakeGateway,
) -> None:
    client = client_of(gateway)
    client.agent("clinica-norte")
    await client.connect()
    assert gateway.headers[0]["Authorization"] == f"Bearer {KEY}"
    assert gateway.headers[0]["pinecall-env"] == "sandbox"
    await client.close()


async def test_a_key_the_gateway_refuses_is_said_with_its_answer(gateway: FakeGateway) -> None:
    client = client_of(gateway, key="pk_wrong")
    client.agent("clinica-norte")
    with pytest.raises(NotConnected, match="403 that key opens nothing here"):
        await client.connect()


async def test_a_slug_another_holds_is_refused_with_the_gateways_sentence() -> None:
    gateway = FakeGateway(taken=frozenset({"clinica-norte"}))
    await gateway.start()
    client = client_of(gateway)
    client.agent("clinica-norte")
    with pytest.raises(Refused, match="refused: clinica-norte is taken"):
        await client.connect()
    await client.close()
    await gateway.close()


async def test_a_socket_the_gateway_closes_while_registering_fails_at_once_with_its_reason() -> (
    None
):
    gateway = FakeGateway(refuses_with=1008)
    await gateway.start()
    client = client_of(gateway)
    client.agent("clinica-norte")
    with pytest.raises(NotConnected, match="this key may not hold an agent"):
        await asyncio.wait_for(client.connect(), 2)
    await gateway.close()


async def test_the_consoles_companion_registers_as_such_and_declares_nothing(
    gateway: FakeGateway,
) -> None:
    client = client_of(gateway)
    client.agent("clinica-norte", answers_dev=True, takes_unclaimed=False)
    await client.connect()
    assert [one["type"] for one in gateway.received] == ["agent.register"]
    data = gateway.commands_of("agent.register")[0]["data"]
    assert isinstance(data, dict)
    assert (data["answers_dev"], data["takes_unclaimed"]) == (True, False)
    await client.close()


async def test_every_entry_is_heard_as_the_gateway_wrote_it_registration_first(
    gateway: FakeGateway,
) -> None:
    client = client_of(gateway)
    client.agent("clinica-norte")
    heard: list[Entry] = []
    client.on_entries(heard.append)
    await client.connect()
    await gateway.emit("clinica-norte", "CA_1", "custom", {"name": "x", "data": {}})
    await gateway.until(lambda: len(heard) == 3)
    assert [entry.type for entry in heard] == ["agent.registered", "agent.configured", "custom"]
    await client.close()


async def test_a_socket_that_dropped_comes_back_and_registers_again(gateway: FakeGateway) -> None:
    client = client_of(gateway)
    client.agent("clinica-norte")
    back: list[str] = []
    client.on_connected(lambda: back.append("connected"))
    await client.connect()
    await gateway.cut()
    await gateway.until(lambda: len(gateway.commands_of("agent.register")) == 2)
    await gateway.until(lambda: back == ["connected", "connected"])
    assert client.connected
    await client.close()


async def test_a_stop_from_the_org_closes_the_socket_for_good_and_says_why(
    gateway: FakeGateway,
) -> None:
    client = client_of(gateway)
    client.agent("clinica-norte")
    why: list[str] = []
    client.on_stopped(why.append)
    await client.connect()
    await gateway.stop("stopped by ana@clinica.es")
    await gateway.until(lambda: why == ["stopped by ana@clinica.es"])
    await asyncio.sleep(0.1)
    assert not client.connected
    assert len(gateway.commands_of("agent.register")) == 1


async def test_a_drain_says_where_the_calls_went_and_waits_for_the_tool_still_running(
    gateway: FakeGateway,
) -> None:
    finish = asyncio.Event()

    async def slow(arguments: JsonObject, call: Call) -> str:
        await finish.wait()
        return "done"

    client = client_of(gateway)
    spec = ToolSpec(name="slow", description="Slow.", parameters={"type": "object"})
    client.agent("clinica-norte", tools=[Tool(spec, slow)])
    await client.connect()
    await gateway.emit(
        "clinica-norte", "CA_1", "tool.call", {"call_id": "tc_1", "name": "slow", "arguments": {}}
    )
    await asyncio.sleep(0.05)
    asyncio.get_running_loop().call_later(0.1, finish.set)
    drained = await client.drain()
    assert (drained.handed, drained.parked, drained.tools, drained.finished) == (1, 0, 1, 1)
    await gateway.until(lambda: len(gateway.commands_of("tool.result")) == 1)
    assert gateway.commands_of("tool.result")[0]["data"] == {
        "call_id": "tc_1",
        "name": "slow",
        "output": "done",
        "duration_s": pytest.approx(0.1, abs=0.2),
    }
    await client.close()


async def test_a_drain_the_gateway_never_answers_is_said_and_the_rest_is_counted() -> None:
    gateway = FakeGateway(holds_drain=True)
    await gateway.start()
    client = client_of(gateway)
    client.agent("clinica-norte")
    said: list[Exception] = []
    client.on_errors(said.append)
    await client.connect()
    assert await client.drain(answer_within_s=0.1) == Drained(0, 0, 0, 0)
    assert "did not answer in 0.1s" in str(said[0])
    await client.close()
    await gateway.close()


async def test_a_search_is_the_gateways_for_the_call_and_answers_its_chunks(
    gateway: FakeGateway,
) -> None:
    gateway.chunks = [{"path": "seguros.md", "heading": "DKV", "text": "Trabajamos con DKV."}]
    client = client_of(gateway)
    found = await client.search("CA_1", "¿trabajan con DKV?", k=3)
    assert [(one.path, one.heading, one.text) for one in found] == [
        ("seguros.md", "DKV", "Trabajamos con DKV.")
    ]
    assert gateway.searched == [
        {"tool": "search", "input": {"query": "¿trabajan con DKV?", "k": 3}, "call": "CA_1"}
    ]


async def test_a_search_the_gateway_refuses_says_its_detail(gateway: FakeGateway) -> None:
    client = client_of(gateway, key="pk_wrong")
    with pytest.raises(Refused, match="403: that key opens nothing here"):
        await client.search("CA_1", "x")


async def test_a_command_whose_data_is_not_its_shape_never_leaves(gateway: FakeGateway) -> None:
    client = client_of(gateway)
    client.agent("clinica-norte")
    await client.connect()
    with pytest.raises(WireError, match=r"agent\.say carries a AgentSay, not a Ping"):
        client.send("agent.say", "clinica-norte", "CA_1", Ping(), "x")
    await client.close()
