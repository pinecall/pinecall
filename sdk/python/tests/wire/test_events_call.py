"""Tests for a call's own events: a key Python cannot spell, the state it opens in, its summary."""

from pinecall.wire._names import JsonObject
from pinecall.wire.events_call import CallStarted, CallSummary


def test_an_event_goes_on_the_wire_by_its_wire_keys_and_absent_fields_stay_absent() -> None:
    started = CallStarted.read(
        {
            "channel": "phone",
            "direction": "inbound",
            "from": "+1",
            "to": "+2",
            "caller": None,
            "started_at": 1.0,
        },
        "call.started",
    )
    assert started.written()["from"] == "+1"
    assert "run" not in started.written()


def test_a_call_started_carries_the_state_it_opens_in_only_when_one_was_asked_for() -> None:
    opened = {"channel": "web", "direction": "inbound", "from": "web_1", "to": "clinica"}
    golden = CallStarted.read(
        {**opened, "caller": None, "started_at": 1.0, "state": {"patient_name": "Ana"}},
        "call.started",
    )
    assert golden.written()["state"] == {"patient_name": "Ana"}
    person = CallStarted.read({**opened, "caller": None, "started_at": 1.0}, "call.started")
    assert "state" not in person.written()


def test_a_summary_says_a_simulated_caller_played_the_call() -> None:
    data: JsonObject = {
        "reason": "caller_hung_up",
        "outcome": "booked",
        "duration_s": 40.0,
        "turns": 6,
        "usage": [],
        "cost": {"usd": 0.01, "rows": [], "unpriced": []},
        "simulated": True,
    }
    summary = CallSummary.read(data, "call.summary")
    assert summary.simulated is True
    assert summary.written() == data


def test_a_written_goldens_summary_names_the_run_that_opened_it() -> None:
    data: JsonObject = {
        "reason": "caller_hung_up",
        "outcome": "booked",
        "duration_s": 40.0,
        "turns": 6,
        "usage": [],
        "cost": {"usd": 0.01, "rows": [], "unpriced": []},
        "run": "run_8f4a2c",
    }
    summary = CallSummary.read(data, "call.summary")
    assert summary.run == "run_8f4a2c"
    assert summary.written() == data
