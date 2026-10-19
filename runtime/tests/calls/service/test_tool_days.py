"""A tool's day: a call's results counted by name, the newest failure kept, the seconds in a histogram."""

from pinecall_runtime.calls import histogram
from pinecall_runtime.calls.service import tool_days
from tests.calls.factories import CALL, a_call_with_tools, a_tool_result, entry


def test_a_calls_results_are_counted_by_tool_with_the_failures_and_the_newest_one() -> None:
    """find_slots worked once; book_slot failed twice, and its last failure is the later, untimed one."""
    rows = {row["tool"]: row for row in tool_days.rows_of(a_call_with_tools())}
    found, booked = rows["find_slots"], rows["book_slot"]
    assert (found["ran"], found["failed"], found["last_error_text"]) == (1, 0, None)
    assert (booked["ran"], booked["failed"]) == (2, 2)
    assert (booked["last_error_call"], booked["last_error_text"]) == (CALL, "book_slot did not answer within 10s")
    assert booked["last_error_at"] == entry(14, "tool.result", {}).ts


def test_only_a_result_with_seconds_is_in_the_histogram() -> None:
    """The timeout of the second book_slot has no duration_s: counted as run and failed, never timed."""
    rows = {row["tool"]: row for row in tool_days.rows_of(a_call_with_tools())}
    assert sum(rows["find_slots"]["buckets"]) == 1
    assert sum(rows["book_slot"]["buckets"]) == 1
    assert histogram.rank(rows["find_slots"]["buckets"], histogram.MEDIAN) == histogram.rank(
        histogram.count_times([0.4]), histogram.MEDIAN
    )


def test_a_result_nobody_can_read_is_left_out_and_raises_nothing() -> None:
    """A tool.result whose data is not a result is skipped, as drift skips a turn it cannot read."""
    broken = entry(1, "tool.result", {"call_id": 7})
    worked = entry(2, "tool.result", a_tool_result("tc_1", "find_slots", seconds=0.1))
    assert [row["tool"] for row in tool_days.rows_of([broken, worked])] == ["find_slots"]
