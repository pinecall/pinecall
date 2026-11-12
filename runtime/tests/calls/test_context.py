"""A call's id: a new one nobody holds, or the one a key names, each the shape a trace id is read from."""

from runtime.calls.context import A_CALL, call_id_of, new_call_id


def test_a_new_call_id_is_nobodys_and_a_keys_is_the_same_each_time() -> None:
    assert new_call_id() != new_call_id()
    assert call_id_of("run_1/3") == call_id_of("run_1/3") != call_id_of("run_1/4")


def test_every_call_id_is_the_prefix_and_thirty_two_hex_digits() -> None:
    for call in (new_call_id(), call_id_of("run_1/3")):
        digits = call.removeprefix(A_CALL)
        assert call.startswith(A_CALL) and len(digits) == 32
        int(digits, 16)
