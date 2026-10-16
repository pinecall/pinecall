"""Reading a log: a page and its state, a stream that comes back from where it was cut."""

import pytest

from pinecall import PinecallError, Refused
from pinecall.client import Client
from pinecall.observe import Observation, Reader, entry_in
from pinecall.wire.events_turn import Custom
from tests.fakes.gateway import KEY, FakeGateway

STARTED: dict[str, object] = {
    "channel": "web",
    "direction": "inbound",
    "from": "web_1",
    "to": "clinica",
    "caller": None,
    "started_at": 1.0,
}


async def test_a_page_is_the_entries_after_the_cursor_their_state_and_the_next_cursor(
    gateway: FakeGateway,
) -> None:
    gateway.write("CA_1", "call.started", STARTED)
    gateway.write("CA_1", "custom", {"name": "cita", "data": {"dia": "martes"}})
    client = Client(gateway.url, KEY)
    page = await client.history(call="CA_1")
    assert [entry.type for entry in page.entries] == ["call.started", "custom"]
    assert (page.state.status, page.state.channel, page.live, page.next) == (
        "active",
        "web",
        True,
        2,
    )
    assert [note.name for note in page.state.custom] == ["cita"]
    later = await client.history(call="CA_1", after=1)
    assert [entry.type for entry in later.entries] == ["custom"]


async def test_a_stream_folds_as_it_goes_and_comes_back_from_the_last_entry_it_saw(
    gateway: FakeGateway,
) -> None:
    gateway.write("CA_1", "call.started", STARTED)
    client = Client(gateway.url, KEY)
    seen: list[Observation] = []
    async for observed in client.observe(call="CA_1"):
        seen.append(observed)
        if len(seen) == 1:
            gateway.write("CA_1", "custom", {"name": "cita", "data": {}})
        if len(seen) == 2:
            break
    assert [one.entry.seq for one in seen] == [1, 2]
    assert isinstance(seen[1].event, Custom)
    assert seen[1].state.status == "active"
    assert gateway.resumed_from[:2] == [None, "1"]


async def test_a_stream_that_never_opened_says_why() -> None:
    gateway = FakeGateway()
    await gateway.start()
    with pytest.raises(Refused, match="403"):
        async for _ in Client(gateway.url, "pk_wrong").observe(call="CA_1"):
            pass
    await gateway.close()


def test_a_log_is_a_calls_or_an_agents_and_one_of_them_is_named() -> None:
    reader = Reader("https://cloud.pinecall.io", KEY, None)
    assert reader.url_of(None, "clinica").endswith("/v1/agents/clinica/calls")
    with pytest.raises(PinecallError, match="name one of call= and agent="):
        reader.url_of("CA_1", "clinica")


def test_an_event_is_its_data_lines_and_a_comment_is_nothing() -> None:
    assert entry_in([": keep-alive"]) is None
    data = (
        '{"seq":1,"ts":1.0,"call":"c","agent":"a","type":"pong","ephemeral":true,"data":{"ts":1.0}}'
    )
    entry = entry_in(["id: 1", f"data: {data}"])
    assert entry is not None
    assert entry.type == "pong"
