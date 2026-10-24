"""The bridge on a gateway: an instance per call, one prompt to open it, only what changed after."""

from collections.abc import AsyncIterator
from typing import Literal, cast

import pytest
from typing_extensions import override

from pinecall import Agent, CallWorld, EventMeta, tool
from pinecall.bridge import Mounted, mount
from pinecall.client import Client
from pinecall.wire._names import JsonObject
from tests.fakes.gateway import KEY, FakeGateway

STARTED: JsonObject = {
    "channel": "web",
    "direction": "inbound",
    "from": "web_1",
    "to": "clinica",
    "caller": None,
    "started_at": 1.0,
    "medium": "text",
}
ENDED: JsonObject = {
    "reason": "caller_hung_up",
    "ended_by": "caller",
    "ended_at": 2.0,
    "duration_s": 1.0,
}


class Clinica(Agent):
    """Eres la recepción de la clínica."""

    stage: Literal["identify", "book"] = "identify"
    patient: str | None = None
    note: str | None = None
    accepts = {"slot.released": ["app"]}  # noqa: RUF012 - the base's ClassVar
    view_template = (
        "{% if patient %}Hablas con {{ patient }}.{% else %}Pide el nombre.{% endif %}"
        "{% if remembers('mañana') %} Ofrece la mañana.{% endif %}"
        "{% if resumed %} No saludes otra vez.{% endif %}"
    )

    @override
    def on_call(self, call: CallWorld) -> None:
        """Note that it opened."""
        self.note = "abierta"

    @override
    def on_event(self, name: str, data: JsonObject, meta: EventMeta) -> None:
        """Note the slot released."""
        self.note = f"{name}:{data['at']}:{meta.source}:{meta.seq}"

    @override
    async def on_end(self, call: CallWorld) -> None:
        """Say how it ended."""
        self.log("fin", {"stage": self.stage})

    @tool(stage="identify")
    def find_patient(self, name: str) -> dict[str, str]:
        """Busca al paciente."""
        self.patient = name
        self.stage = "book"
        return {"name": name}


@pytest.fixture
async def mounted(gateway: FakeGateway) -> AsyncIterator[Mounted]:
    client = Client(gateway.url, KEY)
    held = mount(Clinica, client, slug="clinica")
    await client.connect()
    yield held
    await client.close()


def sent(gateway: FakeGateway, call: str = "CA_1") -> list[tuple[str, dict[str, object]]]:
    return [
        (str(one["type"]), cast("dict[str, object]", one["data"]))
        for one in gateway.received
        if one["call"] == call
    ]


async def opened(gateway: FakeGateway, state: JsonObject | None = None) -> None:
    await gateway.emit(
        "clinica", "CA_1", "call.started", STARTED | ({} if state is None else {"state": state})
    )
    await gateway.until(lambda: any(type_ == "tools.set" for type_, _ in sent(gateway)))


async def test_the_class_is_declared_by_its_layout_its_tools_and_the_events_it_accepts(
    gateway: FakeGateway, mounted: Mounted
) -> None:
    config = cast("dict[str, object]", gateway.commands_of("agent.configure")[0]["data"])["config"]
    assert config == {
        "prompt": [
            {"name": "identity", "region": "static"},
            {"name": "knowledge", "region": "static"},
            {"name": "tools", "region": "static"},
            {"name": "view", "region": "dynamic"},
        ],
        "events": [{"name": "slot.released", "from": ["app"]}],
        "tools": [spec.written() for spec in Clinica().tools()],
    }


async def test_a_call_opens_with_its_prompt_and_tools_first_and_then_one_state(
    gateway: FakeGateway, mounted: Mounted
) -> None:
    await opened(gateway)
    await gateway.until(lambda: any(type_ == "state.set" for type_, _ in sent(gateway)))
    commands = sent(gateway)
    # The prompt first: a state with a pii field is sealed before the gateway reads what follows.
    assert [type_ for type_, _ in commands] == [
        "prompt.set",
        "prompt.set",
        "prompt.set",
        "tools.set",
        "state.set",
    ]
    assert [data["name"] for _, data in commands[0:3]] == ["identity", "tools", "view"]
    assert commands[2][1]["text"] == "Pide el nombre."
    assert "You are in a written chat on a website." in str(commands[0][1]["text"])
    assert commands[4][1] == {
        "state": {"stage": "identify", "patient": None, "note": "abierta"},
        "cause": {"kind": "hook", "hook": "on_call"},
    }
    assert mounted.instance_of("CA_1") is not None


async def test_a_call_opened_in_a_state_opens_there_over_what_on_call_wrote(
    gateway: FakeGateway, mounted: Mounted
) -> None:
    await opened(gateway, {"note": "de un golden", "patient": "Ana"})
    states = [data for type_, data in sent(gateway) if type_ == "state.set"]
    assert states == [
        {
            "state": {"stage": "identify", "patient": "Ana", "note": "de un golden"},
            "cause": {"kind": "hook", "hook": "on_call"},
        }
    ]


async def test_a_tool_call_sends_what_moved_and_the_view_before_its_result(
    gateway: FakeGateway, mounted: Mounted
) -> None:
    await opened(gateway)
    before = len(sent(gateway))
    asked = {"call_id": "tc_1", "name": "find_patient", "arguments": {"name": "Ana"}}
    await gateway.emit("clinica", "CA_1", "tool.call", asked)
    await gateway.until(lambda: any(type_ == "tool.result" for type_, _ in sent(gateway)))
    after = sent(gateway)[before:]
    assert [(type_, data.get("changed")) for type_, data in after if type_ == "state.set"] == [
        ("state.set", ["patient"]),
        ("state.set", ["stage"]),
    ]
    assert [data["name"] for type_, data in after if type_ == "prompt.set"] == ["view"]
    assert [data["tools"] for type_, data in after if type_ == "tools.set"] == [[]]
    result = next(data for type_, data in after if type_ == "tool.result")
    assert result["output"] == {"name": "Ana"}
    # The runtime takes the model's next turn on the result: the prompt must already be there.
    assert [type_ for type_, _ in after][-1] == "tool.result"


async def test_an_accepted_event_runs_on_event_and_its_writes_name_it_as_their_cause(
    gateway: FakeGateway, mounted: Mounted
) -> None:
    await opened(gateway)
    fact = {"name": "slot.released", "data": {"at": "10:00"}, "source": "app"}
    seq = await gateway.emit("clinica", "CA_1", "event.received", fact)
    await gateway.until(lambda: any(data.get("changed") == ["note"] for _, data in sent(gateway)))
    instance = mounted.instance_of("CA_1")
    assert instance is not None
    assert getattr(instance, "note") == f"slot.released:10:00:app:{seq}"  # noqa: B009 - the field under test
    written = next(data for _, data in sent(gateway) if data.get("changed") == ["note"])
    assert written["cause"] == {"kind": "event", "name": "slot.released", "seq": seq}
    assert [data for type_, data in sent(gateway) if type_ == "call.log"] == []


async def test_an_event_from_a_sender_the_class_does_not_accept_never_reaches_it(
    gateway: FakeGateway, mounted: Mounted
) -> None:
    await opened(gateway)
    before = len(sent(gateway))
    fact = {"name": "slot.released", "data": {"at": "10:00"}, "source": "participant"}
    await gateway.emit("clinica", "CA_1", "event.received", fact)
    await gateway.emit("clinica", "CA_1", "custom", {"name": "x", "data": {}})
    await gateway.until(lambda: getattr(mounted.instance_of("CA_1"), "note", None) == "abierta")
    assert sent(gateway)[before:] == []


async def test_what_memory_recalled_reaches_the_view_as_its_answer_to_remembers(
    gateway: FakeGateway, mounted: Mounted
) -> None:
    await opened(gateway)
    recall = {"op": "recall", "facts": [{"text": "prefiere la mañana"}], "took_ms": 3.0}
    await gateway.emit("clinica", "CA_1", "memory.ops", {"ops": [recall]})
    await gateway.until(lambda: sent(gateway)[-1][0] == "prompt.set")
    assert sent(gateway)[-1][1] == {"name": "view", "text": "Pide el nombre. Ofrece la mañana."}


async def test_a_call_handed_over_is_restored_without_on_call_and_sent_whole(
    gateway: FakeGateway, mounted: Mounted
) -> None:
    attached = {
        "app": "app_2",
        "started": STARTED,
        "state": {"stage": "book", "patient": "Ana"},
        "seq": 9,
    }
    await gateway.emit("clinica", "CA_1", "call.attached", attached)
    await gateway.until(lambda: any(type_ == "tools.set" for type_, _ in sent(gateway)))
    instance = mounted.instance_of("CA_1")
    assert instance is not None
    assert getattr(instance, "note") is None  # noqa: B009 - on_call never ran
    assert [data["name"] for type_, data in sent(gateway) if type_ == "prompt.set"] == [
        "identity",
        "tools",
        "view",
    ]
    # P F3: the view's `resumed` was never true on a live call, a handover included.
    view = next(
        data["text"]
        for type_, data in sent(gateway)
        if type_ == "prompt.set" and data["name"] == "view"
    )
    assert view == "Hablas con Ana. No saludes otra vez."


async def test_a_call_that_ends_runs_on_end_whose_line_still_lands_and_is_let_go(
    gateway: FakeGateway, mounted: Mounted
) -> None:
    await opened(gateway)
    await gateway.emit("clinica", "CA_1", "call.ended", ENDED)
    await gateway.until(lambda: any(type_ == "call.log" for type_, _ in sent(gateway)))
    assert next(data for type_, data in sent(gateway) if type_ == "call.log") == {
        "name": "fin",
        "data": {"stage": "identify"},
    }
    assert mounted.instance_of("CA_1") is None
    # The gateway seals on the app's word that the hook ran: said after the hook's last line.
    await gateway.until(lambda: any(type_ == "call.done" for type_, _ in sent(gateway)))
    after = [type_ for type_, _ in sent(gateway) if type_ in ("call.log", "call.done")]
    assert after[-2:] == ["call.log", "call.done"]


class Talker(Agent):
    """Deja una línea en cada gancho."""

    @override
    def on_call(self, call: CallWorld) -> None:
        """Log before anything is followed."""
        self.log("on_call.vio", {"medium": call.medium})

    @override
    def on_end(self, call: CallWorld) -> None:
        """Log after the call ended."""
        self.log("fin", {"ok": True})


async def talking(gateway: FakeGateway, cls: type[Agent], slug: str) -> Client:
    client = Client(gateway.url, KEY)
    mount(cls, client, slug=slug)
    await client.connect()
    await gateway.emit(slug, "CA_1", "call.started", STARTED | {"to": slug})
    return client


async def test_a_line_on_call_logged_lands_though_the_hook_runs_before_anything_is_followed(
    gateway: FakeGateway,
) -> None:
    client = await talking(gateway, Talker, "talker")
    await gateway.until(lambda: any(type_ == "state.set" for type_, _ in sent(gateway)))
    assert [data for type_, data in sent(gateway) if type_ == "call.log"] == [
        {"name": "on_call.vio", "data": {"medium": "text"}}
    ]
    await client.close()


async def test_a_line_on_end_logged_lands_though_the_listeners_are_gone_by_then(
    gateway: FakeGateway,
) -> None:
    client = await talking(gateway, Talker, "talker")
    await gateway.until(lambda: any(type_ == "state.set" for type_, _ in sent(gateway)))
    await gateway.emit("talker", "CA_1", "call.ended", ENDED)
    await gateway.until(lambda: len([t for t, _ in sent(gateway) if t == "call.log"]) == 2)
    assert [data["name"] for type_, data in sent(gateway) if type_ == "call.log"] == [
        "on_call.vio",
        "fin",
    ]
    await client.close()
