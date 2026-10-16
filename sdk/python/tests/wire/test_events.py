"""Tests for the registry of events: every entry of the golden log reads as the model it names."""

import pytest

from pinecall.errors import WireError
from pinecall.wire.events import (
    EPHEMERAL_EVENTS,
    EVENTS,
    TERMINAL_EVENT,
    EvalsSpent,
    event_of,
)
from pinecall.wire.frames import Entry
from tests.wire.golden import golden_entries


def test_the_ephemeral_events_and_the_terminal_one_are_registered() -> None:
    assert set(EVENTS) >= EPHEMERAL_EVENTS
    assert TERMINAL_EVENT in EVENTS


def test_every_entry_of_the_golden_log_is_the_model_its_type_names() -> None:
    entries = golden_entries()
    for entry in entries:
        assert type(event_of(entry)) is EVENTS[entry.type]
    assert [entry.type for entry in entries if not entry.ephemeral][-1] == TERMINAL_EVENT


def test_an_entry_of_a_type_nobody_declared_is_refused_with_its_name() -> None:
    entry = Entry(
        seq=1, ts=1.0, call="c", agent="a", type="call.imagined", ephemeral=False, data={}
    )
    with pytest.raises(WireError, match=r"unknown event type: call\.imagined"):
        event_of(entry)


def test_a_judge_tried_and_an_evals_refusal_on_the_agents_log_read() -> None:
    tried = Entry(
        seq=3,
        ts=1.0,
        call=None,
        agent="clinica-norte",
        type="evals.spent",
        ephemeral=False,
        data={
            "kind": "try",
            "name": "grounded",
            "env": "sandbox",
            "calls": ["c1"],
            "evals": 1,
            "judge_calls": 1,
        },
    )
    assert isinstance(event_of(tried), EvalsSpent)
    refused = Entry(
        seq=4,
        ts=1.0,
        call=None,
        agent="clinica-norte",
        type="credits.exhausted",
        ephemeral=False,
        data={"org": "org_1", "quota": "evals", "used": 500.0, "limit": 500},
    )
    assert event_of(refused).written()["quota"] == "evals"
