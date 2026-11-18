"""A call's id: a new one nobody holds, or the one a key names, each the shape a trace id is read from."""

import pytest

from runtime.calls.context import A_CALL, Route, call_id_of, new_call_id
from runtime.enums import Channel
from runtime.exceptions import ValidationError


def test_a_new_call_id_is_nobodys_and_a_keys_is_the_same_each_time() -> None:
    assert new_call_id() != new_call_id()
    assert call_id_of("run_1/3") == call_id_of("run_1/3") != call_id_of("run_1/4")


def test_every_call_id_is_the_prefix_and_thirty_two_hex_digits() -> None:
    for call in (new_call_id(), call_id_of("run_1/3")):
        digits = call.removeprefix(A_CALL)
        assert call.startswith(A_CALL) and len(digits) == 32
        int(digits, 16)


def test_an_email_route_answers_at_an_address_and_a_phone_one_at_a_number() -> None:
    """An address where a number goes is refused, and a number where an address goes."""
    Route(org="org_1", agent="front-desk", channel=Channel.email, number="help@acme.example")
    Route(org="org_1", agent="front-desk", channel=Channel.sms, number="+14155550134")
    with pytest.raises(ValidationError, match="answers at an address"):
        Route(org="org_1", agent="front-desk", channel=Channel.email, number="+14155550134")
    with pytest.raises(ValidationError, match=r"E\.164"):
        Route(org="org_1", agent="front-desk", channel=Channel.sms, number="help@acme.example")
