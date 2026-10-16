"""A reader's filter: what it named, the ending of its call whatever it named, and on the feed nothing else."""

from pinecall_runtime.calls.fanout import Filter
from tests.calls.factories import entry


def test_a_calls_reader_is_told_the_call_ended_whatever_it_asked_for() -> None:
    only = Filter(types=frozenset({"turn.agent"}))
    assert only.passes(entry(1, "turn.agent", {}))
    assert not only.passes(entry(2, "turn.user", {}))
    assert only.passes(entry(3, "call.ended", {}))


def test_the_feeds_reader_meets_the_types_it_named_and_no_other_calls_ending() -> None:
    """Another call ending on the floor is not this reader's business; the feed never ends."""
    only = Filter(types=frozenset({"release.changed"}), strict=True)
    assert only.passes(entry(1, "release.changed", {}, ephemeral=True))
    assert not only.passes(entry(2, "call.ended", {}))
    assert not only.passes(entry(3, "agent.registered", {}, ephemeral=True))
