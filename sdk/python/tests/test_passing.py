"""A tool call on a served call: a teammate takes it, a task is asked and given, a scene shown."""

from collections.abc import AsyncIterator
from typing import cast

import pytest
from typing_extensions import override

from pinecall import Agent, GetEmail, part, tool
from pinecall.bridge import Mounted, mount
from pinecall.client import Client
from tests.fakes.gateway import KEY, FakeGateway

STARTED = {"channel": "web", "direction": "inbound", "from": "web_1", "to": "front-desk",
           "caller": None, "started_at": 1.0, "medium": "text"}  # fmt: skip
Agenda = part("agenda")


class FrontDesk(Agent):
    """You answer the clinic's phone."""

    tasks = (GetEmail,)
    scenes = {"agenda": "the open times"}  # noqa: RUF012 - the base's ClassVar

    @tool(shows="agenda")
    def look(self, day: str) -> list[str]:
        """Reads the open times of a day."""
        return [f"{day} 9:00"]

    @tool
    async def book(self, day: str) -> dict[str, str]:
        """Books a visit, asking where to send it."""
        return {"day": day, "email": await self.ask(GetEmail)}

    @override
    def screen(self) -> object:
        """The agenda, open while its scene is up."""
        return Agenda(open=self.call.scene == "agenda")


class Billing(Agent):
    """You answer questions about bills."""

    takes = "questions about a bill"

    @tool
    def find_bill(self, number: str) -> str:
        """Finds a bill."""
        return number


def sent(gateway: FakeGateway, kind: str) -> list[dict[str, object]]:
    return [
        cast("dict[str, object]", one["data"])
        for one in gateway.received
        if one["type"] == kind and one["call"] == "CA_1"
    ]


async def called(gateway: FakeGateway, name: str, arguments: dict[str, object], seq: int) -> object:
    before = len(sent(gateway, "tool.result"))
    asked = {"call_id": f"tc_{seq}", "name": name, "arguments": arguments}
    await gateway.emit("front-desk", "CA_1", "tool.call", asked)
    await gateway.until(lambda: len(sent(gateway, "tool.result")) > before)
    return sent(gateway, "tool.result")[-1]["output"]


@pytest.fixture
async def mounted(gateway: FakeGateway) -> AsyncIterator[Mounted]:
    client = Client(gateway.url, KEY)
    team = {FrontDesk: "front-desk", Billing: "billing"}
    held = mount(FrontDesk, client, slug="front-desk", team=team)
    await client.connect()
    await gateway.emit("front-desk", "CA_1", "call.started", STARTED)
    await gateway.until(lambda: bool(sent(gateway, "tools.set")))
    yield held
    await client.close()


async def test_a_teammate_takes_the_call_with_its_own_tools_and_the_pass_on_the_log(
    gateway: FakeGateway, mounted: Mounted
) -> None:
    said = await called(gateway, "transfer_to_billing", {"reason": "a bill"}, 1)
    assert said == "The call is billing's now: go on as billing, without saying it was passed."
    assert isinstance(mounted.instance_of("CA_1"), Billing)
    logged = [one for one in sent(gateway, "call.log") if one.get("name") == "handoff"]
    assert logged[0]["data"] == {"from": "front-desk", "to": "billing", "reason": "a bill"}
    shown = cast("list[dict[str, object]]", sent(gateway, "tools.set")[-1]["tools"])
    assert [one["name"] for one in shown] == ["find_bill"]


async def test_a_tool_that_asks_leaves_one_tool_open_and_finishes_once_it_is_given(
    gateway: FakeGateway, mounted: Mounted
) -> None:
    asked = await called(gateway, "book", {"day": "lunes"}, 1)
    assert str(asked).endswith("Then call give_email.")
    open_ = cast("list[dict[str, object]]", sent(gateway, "tools.set")[-1]["tools"])
    assert [one["name"] for one in open_] == ["give_email"]
    ended = await called(gateway, "give_email", {"email": "Ana@Example.com"}, 2)
    assert ended == {"finished": "book", "result": {"day": "lunes", "email": "ana@example.com"}}


async def test_a_tool_that_shows_a_scene_puts_it_up_on_the_screen_the_state_carries(
    gateway: FakeGateway, mounted: Mounted
) -> None:
    await called(gateway, "look", {"day": "lunes"}, 1)
    screens = [
        one["state"]
        for one in sent(gateway, "state.set")
        if "screen" in cast("dict[str, object]", one["state"])
    ]
    last = cast("dict[str, object]", screens[-1])
    assert last["screen"] == [{"part": "agenda", "props": {"open": True}, "children": []}]
    assert await called(gateway, "show_screen", {"scene": "none"}, 2) == "shown"
