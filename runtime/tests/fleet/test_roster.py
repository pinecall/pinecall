"""A worker's silence is told for each worker: one the feed cannot be told of does not keep the others' from it."""

from pinecall_runtime.fleet.schemas import HeartbeatRequest
from pinecall_runtime.fleet.service.roster import STALE_AFTER_S, Roster
from pinecall_runtime.wire.feed import WorkerChanged


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
