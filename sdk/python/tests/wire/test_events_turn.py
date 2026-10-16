"""Tests for what happens inside a conversation: a state change names what caused it."""

import pytest

from pinecall.errors import WireError
from pinecall.wire.events_turn import StateCauseEvent, StateCauseTool, StateChanged


def test_a_state_change_names_its_cause_and_the_cause_is_told_apart_by_its_kind() -> None:
    by_a_tool = StateChanged.read(
        {
            "state": {"stage": "book"},
            "changed": ["stage"],
            "cause": {"kind": "tool", "tool": "free_slots", "call_id": "tc_1"},
        },
        "state.changed",
    )
    assert isinstance(by_a_tool.cause, StateCauseTool)
    by_a_fact = StateChanged.read(
        {"state": {}, "changed": [], "cause": {"kind": "event", "name": "slot.released", "seq": 9}},
        "state.changed",
    )
    assert isinstance(by_a_fact.cause, StateCauseEvent)


def test_a_cause_of_a_kind_nobody_declared_is_refused() -> None:
    with pytest.raises(WireError, match=r"state\.changed"):
        StateChanged.read({"state": {}, "changed": [], "cause": {"kind": "magic"}}, "state.changed")
