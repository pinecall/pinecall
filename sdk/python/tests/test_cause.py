"""A state.set names who made the write: each write of a tool, a hook and an event handler."""

from collections.abc import AsyncIterator
from typing import Literal, cast

import pytest
from typing_extensions import override

from pinecall import Agent, CallWorld, EventMeta, tool
from pinecall.bridge import mount
from pinecall.client import Client
from pinecall.wire._names import JsonObject
from pinecall.wire.parts import MemoryOp
from tests.fakes.gateway import KEY, FakeGateway

STARTED: JsonObject = {
    "channel": "web",
    "direction": "inbound",
    "from": "web_1",
    "to": "desk",
    "caller": None,
    "started_at": 1.0,
    "medium": "text",
}


class Desk(Agent):
    """Atiende el mostrador."""

    stage: Literal["identify", "choose", "book"] = "identify"
    patient: str = ""
    slot: str = ""
    note: str = ""
    recalled: str = ""
    opened: str = ""
    accepts = {"slot.released": ["app"]}  # noqa: RUF012 - the base's ClassVar

    @override
    def on_call(self, call: CallWorld) -> None:
        """Note that it opened, and move on."""
        self.opened = "yes"
        self.stage = "choose"

    @override
    def on_memory(self, ops: list[MemoryOp], call: CallWorld) -> None:
        """Note that memory spoke."""
        self.recalled = "ops"

    @override
    def on_event(self, name: str, data: JsonObject, meta: EventMeta) -> None:
        """Write two fields."""
        self.slot = str(data["when"])
        self.note = "released"

    @tool
    def look_up(self) -> str:
        """Busca al paciente y avanza la etapa."""
        self.patient = "Ana"
        self.stage = "book"
        return "Ana"


class Quiet(Agent):
    """Nunca escribe al abrir."""

    seen: str = ""


@pytest.fixture
async def client(gateway: FakeGateway) -> AsyncIterator[Client]:
    held = Client(gateway.url, KEY)
    yield held
    await held.close()


async def serving(gateway: FakeGateway, client: Client, cls: type[Agent] = Desk) -> None:
    mount(cls, client, slug="desk")
    await client.connect()
    await gateway.emit("desk", "CA_1", "call.started", STARTED)
    await gateway.until(lambda: any(one["type"] == "state.set" for one in gateway.received))


def writes(gateway: FakeGateway) -> list[tuple[object, object]]:
    return [
        (data.get("changed"), data.get("cause"))
        for data in gateway.data_of("state.set")
        if data.get("changed") is not None
    ]


async def test_each_write_a_tool_makes_names_the_tool_and_the_models_call(
    gateway: FakeGateway, client: Client
) -> None:
    await serving(gateway, client)
    asked: JsonObject = {"call_id": "toolu_7", "name": "look_up", "arguments": {}}
    await gateway.emit("desk", "CA_1", "tool.call", asked)
    await gateway.until(lambda: len(writes(gateway)) == 2)

    by = {"kind": "tool", "tool": "look_up", "call_id": "toolu_7"}
    assert writes(gateway) == [(["patient"], by), (["stage"], by)]


async def test_what_on_call_wrote_is_said_to_be_a_hooks_in_the_one_state_that_carries_it(
    gateway: FakeGateway, client: Client
) -> None:
    await serving(gateway, client)

    opening = gateway.data_of("state.set")[0]
    assert opening["cause"] == {"kind": "hook", "hook": "on_call"}
    assert cast("JsonObject", opening["state"])["opened"] == "yes"


async def test_what_on_memory_wrote_is_said_to_be_a_hooks(
    gateway: FakeGateway, client: Client
) -> None:
    await serving(gateway, client)
    recall = {"op": "recall", "facts": [{"text": "prefiere la mañana"}], "took_ms": 3.0}
    await gateway.emit("desk", "CA_1", "memory.ops", {"ops": [recall]})
    await gateway.until(lambda: len(writes(gateway)) == 1)

    assert writes(gateway) == [(["recalled"], {"kind": "hook", "hook": "on_memory"})]


async def test_each_write_an_event_handler_makes_names_the_event_and_its_entry(
    gateway: FakeGateway, client: Client
) -> None:
    await serving(gateway, client)
    fact = {"name": "slot.released", "data": {"when": "10:15"}, "source": "app"}
    seq = await gateway.emit("desk", "CA_1", "event.received", fact)
    await gateway.until(lambda: len(writes(gateway)) == 2)

    by = {"kind": "event", "name": "slot.released", "seq": seq}
    assert writes(gateway) == [(["slot"], by), (["note"], by)]


async def test_a_call_whose_on_call_wrote_nothing_names_nobody(
    gateway: FakeGateway, client: Client
) -> None:
    await serving(gateway, client, Quiet)

    assert "cause" not in gateway.data_of("state.set")[0]
