"""A call's slowest turns: the three that made the caller wait longest, and where the wait went."""

from pinecall_runtime.calls.service import slow_turns
from tests.calls.factories import CALL, a_call_with_tools, an_agent_turn, entry


def test_a_call_keeps_its_three_slowest_turns_slowest_first() -> None:
    """Four replies timed; the 0.8 s one is dropped, and the others come in order of the wait."""
    rows = slow_turns.rows_of(CALL, a_call_with_tools())
    assert [(row["seq"], row["e2e_s"]) for row in rows] == [(7, 2.0), (10, 1.5), (12, 1.2)]


def test_a_turn_with_a_tool_between_splits_its_wait_into_hearing_thinking_tools_and_speaking() -> None:
    """The first reply: the caller's transcription delay, the model's first token, both tools' seconds, the voice."""
    first = slow_turns.rows_of(CALL, a_call_with_tools())[0]
    assert (first["hears_s"], first["thinks_s"], first["speaks_s"]) == (0.2, 0.5, 0.3)
    assert first["tools_s"] == 0.4 + 0.2
    assert first["name"] == "Marta"
    assert first["at"] == entry(7, "turn.agent", {}).ts


def test_a_reply_after_a_reply_has_no_hearing_and_a_turn_with_no_tool_has_no_tools_seconds() -> None:
    """seq 10 follows an agent turn, not a caller's: nothing was heard for it, and no tool asked in its speech."""
    second = slow_turns.rows_of(CALL, a_call_with_tools())[1]
    assert (second["seq"], second["hears_s"], second["tools_s"], second["thinks_s"]) == (10, None, None, None)


def test_a_turn_with_no_e2e_is_not_a_candidate_and_a_call_with_no_name_has_none() -> None:
    """Text sessions time nothing: no row, and a caller the line did not name is null."""
    untimed = [
        entry(1, "turn.agent", an_agent_turn("s1")),
        entry(2, "turn.agent", an_agent_turn("s2", e2e_latency=3.0)),
    ]
    (only,) = slow_turns.rows_of(CALL, untimed)
    assert (only["seq"], only["name"]) == (2, None)
