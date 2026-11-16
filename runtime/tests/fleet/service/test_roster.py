"""A worker's silence is told for each worker: one the feed cannot be told of does not keep the others' from it."""

from runtime.fleet.service.roster import Roster
from runtime.fleet.service.slots import OFFERABLE_WITHIN_S, STALE_AFTER_S
from runtime.wire.feed import WorkerChanged
from runtime.wire.worker import HeartbeatRequest


def beat(worker: str) -> HeartbeatRequest:
    """A worker that holds nothing and is not loaded."""
    return HeartbeatRequest(fleet="pinecall", worker=worker, active=0, max_jobs=4, load=0.0, draining=False)


def test_a_silent_worker_the_feed_cannot_be_told_of_does_not_keep_the_others_from_being_told() -> None:
    told: list[WorkerChanged] = []

    def on_change(change: WorkerChanged) -> None:
        if change.up:
            return
        if change.worker == "worker-a":
            raise RuntimeError("the feed could not be told")
        told.append(change)

    roster = Roster(on_change=on_change)
    for worker in ("worker-a", "worker-b"):
        roster.report_heartbeat(beat(worker), now=0.0)
    roster.forget_silent(STALE_AFTER_S + 1)
    assert [change.worker for change in told] == ["worker-b"]
    roster.forget_silent(STALE_AFTER_S + 2)
    assert [change.worker for change in told] == ["worker-b"], "each is told once"


# 2026-11-16: a worker that died had beaten seconds before, and for two heartbeats more it was the
# worker with every seat free. Its own call was offered back to it, and any new call would have been.
def test_a_worker_said_gone_is_named_until_it_is_heard_again_or_its_silence_says_it() -> None:
    roster = Roster()
    answered = roster.report_heartbeat(beat("worker-a"), now=100.0)
    assert not answered.cordoned
    named = roster.workers[("pinecall", "worker-a")].model_copy(update={"agent_name": "pinecall/worker-a"})
    roster.workers[("pinecall", "worker-a")] = named
    assert roster.list_gone("pinecall", 101.0) == []
    roster.say_gone("pinecall/worker-a", 101.0)
    assert roster.list_gone("pinecall", 102.0) == ["pinecall/worker-a"]
    assert roster.list_gone("another", 102.0) == []
    assert roster.list_gone("pinecall", 101.0 + OFFERABLE_WITHIN_S + 1) == [], "its silence says it by then"
    roster.say_gone("a name nobody beat under", 101.0)
    heard = named.model_copy(update={"seen_at": 103.0})
    roster.workers[("pinecall", "worker-a")] = heard
    assert roster.list_gone("pinecall", 104.0) == [], "it beat after it was said gone: it is back"


def test_a_departure_one_gateway_says_is_heard_by_the_other_in_its_share() -> None:
    roster = Roster()
    roster.report_heartbeat(beat("worker-a"), now=100.0)
    key = ("pinecall", "worker-a")
    roster.workers[key] = roster.workers[key].model_copy(update={"agent_name": "pinecall/worker-a"})
    roster.say_gone("pinecall/worker-a", 101.0)
    said = roster.shared.gathered
    assert said is not None
    assert [(gone.fleet, gone.worker, gone.at) for gone in said().departures] == [("pinecall", "worker-a", 101.0)]
    roster.forget_silent(101.0 + OFFERABLE_WITHIN_S + 1)
    assert said().departures == (), "a departure past the two heartbeats is spent"
