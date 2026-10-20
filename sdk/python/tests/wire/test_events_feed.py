"""Tests for the feed's events: a change no log holds goes on the wire by ids alone, ephemeral."""

from pinecall.wire.events import EPHEMERAL_EVENTS, EVENTS
from pinecall.wire.events_feed import JudgeBroke, ToolFailed, ToolRan


def test_a_tool_that_ran_is_said_by_its_call_agent_name_and_seconds_alone() -> None:
    ran = ToolRan.read(
        {"call": "call_1", "agent": "front-desk", "name": "takeMessage", "duration_s": 0.4},
        "tool.ran",
    )
    assert ran.written() == {
        "call": "call_1",
        "agent": "front-desk",
        "name": "takeMessage",
        "duration_s": 0.4,
    }


def test_a_tool_that_failed_may_carry_no_seconds() -> None:
    failed = ToolFailed.read(
        {"call": "call_1", "agent": "front-desk", "name": "takeMessage", "duration_s": None},
        "tool.failed",
    )
    assert failed.duration_s is None


def test_a_judge_that_broke_names_the_judge_and_never_its_reason() -> None:
    broke = JudgeBroke.read(
        {"call": "call_1", "agent": "front-desk", "judge": "tone"}, "judge.broke"
    )
    assert set(broke.written()) == {"call", "agent", "judge"}


def test_the_feeds_events_are_in_the_registry_and_ephemeral() -> None:
    for name in (
        "tool.ran",
        "tool.failed",
        "judge.broke",
        "run.changed",
        "release.changed",
        "worker.changed",
    ):
        assert name in EVENTS
        assert name in EPHEMERAL_EVENTS
