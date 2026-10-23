"""What a class's own failure leaves on its call: a hook that raised, a view that failed."""

from typing import Literal, cast

from typing_extensions import override

from pinecall import Agent, CallWorld, EventMeta, tool
from pinecall.wire._names import JsonObject
from tests.fakes.gateway import FakeGateway
from tests.test_bridge import ENDED, sent, talking


class Broken(Agent):
    """Su vista falla al dibujarse."""

    view_template = "{{ 1 // 0 }}"
    stage: Literal["open"] = "open"

    @tool
    def ping(self) -> str:
        """Responde."""
        return "pong"


async def test_a_view_that_cannot_be_rendered_is_logged_and_the_call_goes_on(
    gateway: FakeGateway,
) -> None:
    client = await talking(gateway, Broken, "broken")
    await gateway.until(lambda: any(type_ == "state.set" for type_, _ in sent(gateway)))
    failed = [data for type_, data in sent(gateway) if type_ == "call.log"]
    assert [data["name"] for data in failed] == ["render.failed"]
    assert "division" in str(cast("JsonObject", failed[0]["data"])["message"])
    asked: JsonObject = {"call_id": "tc_1", "name": "ping", "arguments": {}}
    await gateway.emit("broken", "CA_1", "tool.call", asked)
    await gateway.until(lambda: any(type_ == "tool.result" for type_, _ in sent(gateway)))
    result = next(data for type_, data in sent(gateway) if type_ == "tool.result")
    assert result["output"] == "pong"
    await client.close()


class Fragile(Agent):
    """Cada gancho falla, después de escribir lo que tenía."""

    accepts = {"slot.released": ["app"]}  # noqa: RUF012 - the base's ClassVar
    opened: str = ""
    slot: str = ""

    @override
    def on_call(self, call: CallWorld) -> None:
        """Write, then fail."""
        self.opened = "partly"
        raise ValueError("the agenda is down")

    @override
    def on_event(self, name: str, data: JsonObject, meta: EventMeta) -> None:
        """Write, then fail."""
        self.slot = str(data["when"])
        raise ValueError("no such slot")

    @override
    async def on_end(self, call: CallWorld) -> None:
        """Log, then fail."""
        self.log("fin", {"ok": True})
        raise ValueError("could not close")


def hook_failures(gateway: FakeGateway) -> list[JsonObject]:
    return [
        cast("JsonObject", data["data"])
        for type_, data in sent(gateway)
        if type_ == "call.log" and data["name"] == "hook.failed"
    ]


async def test_a_hook_that_raises_is_named_in_the_log_and_the_call_opens_anyway(
    gateway: FakeGateway,
) -> None:
    client = await talking(gateway, Fragile, "fragile")
    await gateway.until(lambda: any(type_ == "state.set" for type_, _ in sent(gateway)))
    assert hook_failures(gateway) == [
        {"hook": "on_call", "error": "ValueError", "message": "the agenda is down"}
    ]
    opening = next(data for type_, data in sent(gateway) if type_ == "state.set")
    assert cast("JsonObject", opening["state"])["opened"] == "partly"
    await client.close()


async def test_an_event_hook_that_raises_is_named_with_its_event_and_the_next_still_runs(
    gateway: FakeGateway,
) -> None:
    client = await talking(gateway, Fragile, "fragile")
    await gateway.until(lambda: any(type_ == "state.set" for type_, _ in sent(gateway)))
    for when in ("10:15", "11:00"):
        fact = {"name": "slot.released", "data": {"when": when}, "source": "app"}
        await gateway.emit("fragile", "CA_1", "event.received", fact)
    await gateway.until(lambda: len(hook_failures(gateway)) == 3)
    assert (
        hook_failures(gateway)[1:]
        == [
            {
                "hook": "on_event",
                "event": "slot.released",
                "error": "ValueError",
                "message": "no such slot",
            }
        ]
        * 2
    )
    await client.close()


async def test_an_on_end_that_raises_is_named_and_its_own_line_still_lands_and_the_call_is_let_go(
    gateway: FakeGateway,
) -> None:
    client = await talking(gateway, Fragile, "fragile")
    await gateway.until(lambda: any(type_ == "state.set" for type_, _ in sent(gateway)))
    await gateway.emit("fragile", "CA_1", "call.ended", ENDED)
    await gateway.until(lambda: len(hook_failures(gateway)) == 2)
    assert hook_failures(gateway)[1]["hook"] == "on_end"
    assert "fin" in [data["name"] for type_, data in sent(gateway) if type_ == "call.log"]
    await client.close()
