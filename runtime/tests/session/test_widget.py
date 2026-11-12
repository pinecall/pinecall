"""A widget's channel: the public log of its own call, the events it may send, its hang-up."""

import asyncio
import json
from collections.abc import AsyncIterator, Callable

import pytest
from livekit import rtc

from runtime.agents.declaration import Declaration
from runtime.calls.log.log import Log
from runtime.calls.log.store import Store
from runtime.calls.projection import Audience, project_entry, project_state
from runtime.enums import Channel
from runtime.kit.text import JsonObject
from runtime.session.call import Call
from runtime.session.widget import EVENT, HANGUP, LOG, REPLAY, SNAPSHOT, Reading, Widget
from runtime.wire.base import Entry
from runtime.wire.parts import Visibility
from tests.conftest import needs_the_database
from tests.fakes.livekit import Room, seat
from tests.session.conftest import Box, context_of

WIDGET = {"pinecall.scope": "talk"}
RELIABLE = rtc.DataPacketKind.KIND_RELIABLE
AGENT = Declaration(
    slug="clinica-norte",
    events={"clicked": frozenset({"participant"})},
    state_fields={"card": "pii"},
)


# As the worker reads its call for a widget: the state and each entry projected for its seat.
def _reading(log: Log, store: Store, config: Declaration) -> Reading:
    async def state(viewer: str) -> tuple[JsonObject, int]:
        assert log.call is not None
        projected = project_state(await log.snapshot(), Audience("public", viewer), config)
        return projected, await store.seq_of(log.call)

    async def since(after: int) -> AsyncIterator[Entry]:
        assert log.call is not None
        for entry in await store.whole_of(log.call, after=after):
            yield entry

    async def tail(after: int) -> AsyncIterator[Entry]:
        async for entry in log.stream(after=after):
            if entry.type != "log.caught_up":
                yield entry

    def public(entry: Entry, viewer: str) -> JsonObject | None:
        return project_entry(entry, Audience("public", viewer), config)

    return Reading(state=state, since=since, tail=tail, public=public)


type Widgets = Callable[..., tuple[Widget, Room]]


@pytest.fixture
async def widgets(box: Box, store: Store) -> AsyncIterator[Widgets]:
    """A widget's channel on the call, as many as a test opens; their writers closed after it."""
    opened: list[Call] = []

    def open_one(visibility: dict[str, Visibility] | None = None) -> tuple[Widget, Room]:
        assert box.log.call is not None
        config = Declaration(slug=AGENT.slug, events=AGENT.events, state_fields=visibility or AGENT.state_fields)
        call = Call(context_of(box.log.call, Channel.web), config, box)
        call.writing.open()
        opened.append(call)
        offline = Room(box.log.call)
        widget = Widget(call, offline, _reading(box.log, store, config))
        widget.watch()
        return widget, offline

    yield open_one
    for call in opened:
        await call.writing.close(5)


def _sent(offline: Room, topic: str) -> list[dict[str, object]]:
    return [json.loads(packed) for sent, packed, _ in offline.me.published if sent == topic]


async def _settled() -> None:
    await asyncio.sleep(0.1)


@needs_the_database
async def test_a_widget_gets_the_snapshot_first_and_then_the_log_as_it_grows(
    widgets: Widgets, box: Box, store: Store
) -> None:
    await box.log.append("state.changed", {"state": {"step": 1}, "changed": ["step"]})
    widget, offline = widgets()
    offline.emit("participant_connected", seat("visitor_1", attributes=WIDGET))
    await _settled()
    await box.log.append("state.changed", {"state": {"step": 2}, "changed": ["step"]})
    await _settled()
    widget.stop()
    (snapshot,) = _sent(offline, SNAPSHOT)
    assert snapshot["last_seq"] == 1
    assert [entry["seq"] for entry in _sent(offline, LOG)] == [2]


@needs_the_database
async def test_nothing_of_the_tenants_leaves_for_the_browser(widgets: Widgets, box: Box, store: Store) -> None:
    await box.log.append("state.changed", {"state": {"card": "4111"}, "changed": ["card"]})
    widget, offline = widgets()
    offline.emit("participant_connected", seat("visitor_1", attributes=WIDGET))
    await _settled()
    widget.stop()
    assert "4111" not in json.dumps(_sent(offline, SNAPSHOT))


@needs_the_database
async def test_a_replay_resends_from_the_cursor_and_ends_with_caught_up(
    widgets: Widgets, box: Box, store: Store
) -> None:
    for step in (1, 2, 3):
        await box.log.append("state.changed", {"state": {"step": step}, "changed": ["step"]})
    widget, offline = widgets()
    visitor = seat("visitor_1", attributes=WIDGET)
    offline.emit("participant_connected", visitor)
    await _settled()
    offline.emit(
        "data_received",
        rtc.DataPacket(data=b'{"after": 1}', kind=RELIABLE, participant=visitor, topic=REPLAY),
    )
    await _settled()
    widget.stop()
    replayed = [(entry["type"], entry["seq"]) for entry in _sent(offline, LOG)]
    assert replayed == [("state.changed", 2), ("state.changed", 3), ("log.caught_up", 3)]


@needs_the_database
async def test_a_declared_event_from_a_widget_lands_as_event_received_with_its_identity(
    widgets: Widgets, box: Box, store: Store, call: str
) -> None:
    widget, offline = widgets()
    visitor = seat("visitor_1", attributes=WIDGET)
    packet = json.dumps({"name": "clicked", "data": {"x": 1}}).encode()
    offline.emit(
        "data_received",
        rtc.DataPacket(data=packet, kind=RELIABLE, participant=visitor, topic=EVENT),
    )
    await asyncio.gather(*widget.answering)
    await widget.call.writing.flush(5)
    widget.stop()
    (received,) = await store.whole_of(call)
    assert (received.type, received.data["identity"], received.data["source"]) == (
        "event.received",
        "visitor_1",
        "participant",
    )


@needs_the_database
async def test_an_undeclared_or_malformed_event_never_reaches_the_log(
    widgets: Widgets, box: Box, store: Store, call: str
) -> None:
    widget, offline = widgets()
    visitor = seat("visitor_1", attributes=WIDGET)
    for packet in (b'{"name": "paid", "data": {}}', b'{"name": "clicked"}', b"not json"):
        offline.emit(
            "data_received",
            rtc.DataPacket(data=packet, kind=RELIABLE, participant=visitor, topic=EVENT),
        )
    await asyncio.gather(*widget.answering)
    await widget.call.writing.flush(5)
    widget.stop()
    assert await store.whole_of(call) == []


# A reload and a hang-up both disconnect the seat: the hang-up is said, and only a widget says it.
@needs_the_database
async def test_a_widgets_hang_up_ends_its_call_and_nobody_elses_does(widgets: Widgets, box: Box, store: Store) -> None:
    widget, offline = widgets()
    hung_up: list[str] = []
    widget.when_hung_up(lambda: hung_up.append("caller"))
    stranger = seat("ana", attributes={"pinecall.scope": "supervise"})
    visitor = seat("visitor_1", attributes=WIDGET)
    for who in (stranger, visitor):
        offline.emit(
            "data_received",
            rtc.DataPacket(data=b"{}", kind=RELIABLE, participant=who, topic=HANGUP),
        )
    widget.stop()
    assert hung_up == ["caller"]


@needs_the_database
async def test_only_a_widgets_seat_speaks_on_the_channel(widgets: Widgets, box: Box, store: Store, call: str) -> None:
    widget, offline = widgets()
    stranger = seat("ana", attributes={"pinecall.scope": "supervise"})
    packet = json.dumps({"name": "clicked", "data": {}}).encode()
    offline.emit(
        "data_received",
        rtc.DataPacket(data=packet, kind=RELIABLE, participant=stranger, topic=EVENT),
    )
    offline.emit("participant_connected", stranger)
    await _settled()
    widget.stop()
    assert await store.whole_of(call) == []
    assert offline.me.published == []


@needs_the_database
async def test_a_widget_that_left_is_sent_nothing_more(widgets: Widgets, box: Box, store: Store) -> None:
    widget, offline = widgets()
    visitor = seat("visitor_1", attributes=WIDGET)
    offline.emit("participant_connected", visitor)
    await _settled()
    offline.emit("participant_disconnected", visitor)
    await box.log.append("state.changed", {"state": {"step": 2}, "changed": ["step"]})
    await _settled()
    widget.stop()
    assert _sent(offline, LOG) == []


@needs_the_database
async def test_stopping_cancels_the_tail_and_lets_go_of_the_room(widgets: Widgets, box: Box, store: Store) -> None:
    widget, offline = widgets()
    offline.emit("participant_connected", seat("visitor_1", attributes=WIDGET))
    await _settled()
    tailing = widget.tailing
    widget.stop()
    await asyncio.sleep(0)
    assert tailing is not None
    assert tailing.cancelled() or tailing.done()
    offline.emit("participant_connected", seat("visitor_2", attributes=WIDGET))
    await _settled()
    assert len(_sent(offline, SNAPSHOT)) == 1


@needs_the_database
async def test_a_widget_joining_late_is_caught_up_and_then_nothing_arrives_twice(
    widgets: Widgets, box: Box, store: Store
) -> None:
    widget, offline = widgets()
    first = seat("visitor_1", attributes=WIDGET)
    offline.emit("participant_connected", first)
    await _settled()
    await box.log.append("state.changed", {"state": {"step": 1}, "changed": ["step"]})
    await _settled()
    late = seat("visitor_2", attributes=WIDGET)
    offline.emit("participant_connected", late)
    await _settled()
    await box.log.append("state.changed", {"state": {"step": 2}, "changed": ["step"]})
    await _settled()
    widget.stop()
    to_the_late = [
        json.loads(packed)["seq"] for topic, packed, to in offline.me.published if topic == LOG and to == ["visitor_2"]
    ]
    assert to_the_late == sorted(set(to_the_late))
    assert to_the_late[-1] == 2


# A widget the room could not publish to (it left as the entry went) ended the call's one tail, and
# every widget of the call was left on the state it had.
@needs_the_database
async def test_a_widget_that_cannot_be_sent_an_entry_does_not_end_the_tail_nor_stale_the_others(
    widgets: Widgets, box: Box, store: Store, call: str, caplog: pytest.LogCaptureFixture
) -> None:
    widget, offline = widgets()
    for visitor in ("web_gone", "web_here"):
        offline.emit("participant_connected", seat(visitor, attributes=WIDGET))
    await _settled()
    offline.me.left.add("web_gone")
    for step in (1, 2):
        await box.log.append("state.changed", {"state": {"step": step}, "changed": ["step"]})
    await _settled()
    # The one that could not be sent is counted as sent too: it is not sent the same entry for ever.
    assert widget.audience == {"web_gone": 2, "web_here": 2}
    widget.stop()
    to_here = [
        json.loads(packed)["seq"] for topic, packed, to in offline.me.published if topic == LOG and to == ["web_here"]
    ]
    assert to_here == [1, 2]
    assert f"sending an entry to a widget failed on {call} for web_gone" in caplog.text
