"""What the log takes from a worker: the protocol's own words, and a start and an end the gateway can read."""

import pytest

from pinecall_runtime.calls.service.serving import check_entry
from pinecall_runtime.exceptions import Forbidden, ValidationError
from pinecall_runtime.kit.text import JsonObject

A_START: JsonObject = {
    "channel": "web",
    "direction": "inbound",
    "from": "web_1",
    "to": "clinica-norte",
    "caller": None,
    "started_at": 1.0,
}
AN_END: JsonObject = {"reason": "caller_hung_up", "ended_by": "caller", "ended_at": 2.0, "duration_s": 1.0}


# M B10 (2026-10-23): a call.started with no `caller` was taken, and the seal of its call answered
# 500 for ever. `Contact | null` is required (wire/events-call.md): null is an answer, absent is not.
def test_a_call_started_with_no_caller_is_refused_naming_the_field() -> None:
    without = {name: value for name, value in A_START.items() if name != "caller"}
    with pytest.raises(ValidationError, match=r"call\.started: .*\ncaller\n"):
        check_entry("call.started", without)


def test_a_call_started_whose_caller_is_null_or_known_is_taken() -> None:
    check_entry("call.started", A_START)
    check_entry("call.started", {**A_START, "caller": {"id": "ct_9", "name": "Marta"}})


def test_a_call_ended_the_gateway_cannot_read_is_refused() -> None:
    with pytest.raises(ValidationError, match=r"call\.ended: "):
        check_entry("call.ended", {**AN_END, "reason": "of its own accord"})
    check_entry("call.ended", AN_END)


def test_the_other_entries_are_not_read_at_the_endpoint() -> None:
    check_entry("custom", {"name": "anything", "data": {"at": "all"}})


def test_a_type_the_protocol_lacks_and_one_the_gateway_writes_are_refused_before_any_shape() -> None:
    with pytest.raises(ValidationError, match="no event is called"):
        check_entry("call.begun", A_START)
    with pytest.raises(Forbidden, match="written by the gateway itself"):
        check_entry("call.summary", {})
