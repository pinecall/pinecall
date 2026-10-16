"""A call as the app holds it: what each event teaches it, and the command each method sends."""

from pinecall._calls import Call, CallBook, day_of
from pinecall.wire._names import JsonObject
from pinecall.wire.events_call import CallAttached, CallClaimed, CallStarted
from pinecall.wire.events_turn import StateChanged
from pinecall.wire.frames import WireModel

STARTED: JsonObject = {
    "channel": "phone",
    "direction": "inbound",
    "from": "+34600",
    "to": "+34910",
    "caller": {"name": "Ana"},
    "started_at": 1786537500.0,
    "medium": "voice",
}


def a_call() -> tuple[Call, list[tuple[str, str | None, JsonObject]]]:
    sent: list[tuple[str, str | None, JsonObject]] = []

    def send(type_: str, call: str | None, data: WireModel) -> None:
        sent.append((type_, call, data.written()))

    return Call("CA_1", send, 1786537500.0, lambda error: None), sent


def test_a_started_call_knows_its_line_and_is_active() -> None:
    call, _ = a_call()
    call.take("call.started", CallStarted.read(STARTED, "call.started"))
    assert (call.status, call.channel, call.medium, call.from_, call.to) == (
        "active",
        "phone",
        "voice",
        "+34600",
        "+34910",
    )
    assert call.contact is not None
    assert call.contact.name == "Ana"


def test_a_runs_call_runs_on_the_day_call_started_names() -> None:
    call, _ = a_call()
    pinned = {**STARTED, "run": "run_1", "today": "2026-09-17"}
    call.take("call.started", CallStarted.read(pinned, "call.started"))
    assert call.today == "2026-09-17"
    call.take("call.started", CallStarted.read(STARTED, "call.started"))
    assert call.today == "2026-09-17"


def test_a_call_handed_over_keeps_the_day_it_opened_its_state_and_its_code() -> None:
    call, _ = a_call()
    handed: JsonObject = {
        "app": "app_2",
        "started": STARTED,
        "state": {"stage": "book"},
        "seq": 9,
        "claimed": "4821",
    }
    attached = CallAttached.read(handed, "call.attached")
    call.take("call.attached", attached)
    assert (call.status, call.state, call.claimed) == ("active", {"stage": "book"}, "4821")
    assert call.today == day_of(1786537500.0)


def test_the_state_and_the_code_follow_what_the_log_says() -> None:
    call, _ = a_call()
    call.take(
        "state.changed", StateChanged.read({"state": {"a": 1}, "changed": ["a"]}, "state.changed")
    )
    call.take("call.claimed", CallClaimed.read({"code": "1234", "via": "keypad"}, "call.claimed"))
    assert (call.state, call.claimed) == ({"a": 1}, "1234")


def test_each_method_sends_one_command_and_says_only_what_it_was_given() -> None:
    call, sent = a_call()
    call.say("Un momento.")
    call.reply("Ofrece el martes.", allow_interruptions=False)
    call.set_state({"stage": "book"}, ["stage"])
    call.hangup()
    call.log("cita.reservada")
    assert sent == [
        ("agent.say", "CA_1", {"text": "Un momento."}),
        (
            "agent.reply",
            "CA_1",
            {"instructions": "Ofrece el martes.", "allow_interruptions": False},
        ),
        ("state.set", "CA_1", {"state": {"stage": "book"}, "changed": ["stage"]}),
        ("call.hangup", "CA_1", {}),
        ("call.log", "CA_1", {"name": "cita.reservada", "data": {}}),
    ]
    assert call.state == {"stage": "book"}


def test_the_book_opens_a_call_on_first_sight_and_forgets_it_once_it_ended() -> None:
    def sent(type_: str, call: str | None, data: WireModel) -> None: ...

    book = CallBook(sent, lambda error: None)
    call = book.of("CA_1", 1.0)
    assert book.of("CA_1", 2.0) is call
    book.forget(call)
    assert book.live == [call]
    call.status = "ended"
    book.forget(call)
    assert book.live == []
