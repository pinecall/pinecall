"""The one rule of a worker's slots: heard, failing or accepting, the slots it has free, and the worker chosen."""

from collections.abc import Collection, Iterable, Mapping, Sequence
from typing import Literal

from runtime.wire.signal import WorkerStatus

type WorkerState = Literal["gone", "cordoned", "draining", "accepting", "failing", "full"]

# Every line a worker is measured against, in one place. Until 2026-11 they stood in two modules:
# the roster counted a worker heard for 30 s and accepting by its load, the dispatcher offered a
# call only to one heard for 12 s with a slot left after the offers in flight, and a visitor let
# in by the first was sent the overflow's sentence by the second.

# A worker beats this often.
HEARTBEAT_S = 5.0
# A worker silent this long is no longer capacity.
STALE_AFTER_S = 30.0
# Two heartbeats and a margin: a worker unheard this long may be gone, and LiveKit would keep a
# dead one for 15 minutes; it is not offered a call until it is heard again.
OFFERABLE_WITHIN_S = 2 * HEARTBEAT_S + 2
# A silent worker stays listed, as gone, this long.
FORGOTTEN_AFTER_S = 3600.0

# LiveKit's line, the same on both of its sides: livekit-server's agent.DefaultTargetLoad
# (pkg/agent/config.go; a job is offered to a worker whose reported load is under it) and
# livekit-agents' load_threshold (the worker declines at or over it). A worker gated on CPU
# reports its share of the machine, which is that scale. A worker that counts its calls reports
# 0.7 times its calls over its slots to LiveKit (heartbeat.Load), so LiveKit's full is its last
# slot, and calls over slots to the gateway, full at 1.0: on 2026-10-02 it reported calls over
# slots to both, and LiveKit stopped at 0.7 of them while the gateway still counted slots free.
REFUSED_AT = 0.7
EVERY_SLOT = 1.0

# A worker up but bad: at least half the calls that ended in its last minute ended in an error,
# judged on four calls at least, or its callers waited over five seconds for first audio at the
# p95, over twenty turns at least. Set so they change nothing a healthy worker does.
FAILED_SHARE = 0.5
ENDED_TO_JUDGE = 4
SLOW_FIRST_AUDIO_S = 5.0
TURNS_TO_JUDGE = 20


def is_heard(worker: WorkerStatus, now: float, within: float = STALE_AFTER_S) -> bool:
    """Whether the worker's last heartbeat is recent enough to count."""
    return now - worker.seen_at <= within


# A gateway that just started rebuilds its roster from the next heartbeats, five seconds: until a
# worker of the fleet is heard, nobody can say the fleet is full.
def is_any_heard(workers: Iterable[WorkerStatus], now: float) -> bool:
    """Whether any worker of the fleet was heard in time to be offered a call, whatever it is doing."""
    return any(is_heard(worker, now, OFFERABLE_WITHIN_S) for worker in workers)


def is_failing(worker: WorkerStatus) -> bool:
    """Whether the worker's last minute is past the line: its calls fail, or its callers wait."""
    ended, failed = worker.ended or 0, worker.failed or 0
    if ended >= ENDED_TO_JUDGE and failed / ended >= FAILED_SHARE:
        return True
    slow = worker.first_audio_p95_s
    return (worker.turns or 0) >= TURNS_TO_JUDGE and slow is not None and slow > SLOW_FIRST_AUDIO_S


# A failing worker is not counted while another of its fleet accepts and is not failing: the line
# never empties a fleet, so a box of one worker per env keeps counting its one.
def accepting_of(workers: Iterable[WorkerStatus], now: float) -> list[WorkerStatus]:
    """The fleet's workers counted as accepting: up and under the line, and not failing."""
    accepting = [worker for worker in workers if _is_accepting_now(worker, now)]
    sound = [worker for worker in accepting if not is_failing(worker)]
    return sound or accepting


def state_of(worker: WorkerStatus, fleet: Sequence[WorkerStatus], now: float) -> WorkerState:
    """How the roster counts the worker among its fleet's: gone, cordoned, draining, and so on."""
    if not is_heard(worker, now):
        return "gone"
    if worker.cordoned:
        return "cordoned"
    if worker.draining:
        return "draining"
    if worker in accepting_of(fleet, now):
        return "accepting"
    return "failing" if _is_accepting_now(worker, now) else "full"


# A worker gated on its CPU has no count of slots: one call at a time is offered to it, under
# LiveKit's line.
def free_slots(worker: WorkerStatus, in_flight: Mapping[str, int]) -> int:
    """The slots a worker has free, its calls and the ones offered to it not yet opened taken."""
    offered = in_flight.get(worker.agent_name or "", 0)
    if worker.max_jobs is None:
        return 1 if worker.load < REFUSED_AT and offered == 0 else 0
    return worker.max_jobs - worker.active - offered


def choose_worker(
    workers: Collection[WorkerStatus], in_flight: Mapping[str, int], now: float, not_these: Collection[str] = ()
) -> WorkerStatus | None:
    """The worker to offer a call to, or None when no worker of the fleet has a slot."""
    candidates = [
        worker
        for worker in accepting_of(workers, now)
        if worker.agent_name is not None
        and worker.agent_name not in not_these
        and is_heard(worker, now, OFFERABLE_WITHIN_S)
        and free_slots(worker, in_flight) > 0
    ]
    return max(candidates, key=lambda worker: (free_slots(worker, in_flight), -worker.load), default=None)


# The one answer to "is there room for a call": a visitor's token, a simulation and the dispatcher
# all ask it, so nobody is let in by one count and sent the overflow's sentence by another. A
# worker's heartbeat says its slots; a gateway that heard no worker yet cannot say the fleet is full.
def has_a_slot(workers: Collection[WorkerStatus], in_flight: Mapping[str, int], now: float) -> bool:
    """Whether a call offered now would find a worker with a slot; True while no worker was heard."""
    return not is_any_heard(workers, now) or choose_worker(workers, in_flight, now) is not None


# The heartbeat's `full`, as the gateway of the release before 2026-11 answers it: by the heartbeats
# alone, the offers in flight not counted, and never for a fleet nobody heard from. Nothing here
# decides by it: it goes with `HeartbeatResponse.full`, once no worker of that release beats.
def accepts_nobody(workers: Iterable[WorkerStatus], now: float) -> bool:
    """Whether the fleet's workers heard from lately are all refusing calls."""
    up = [worker for worker in workers if is_heard(worker, now)]
    return bool(up) and not accepting_of(up, now)


def _line_of(max_jobs: int | None) -> float:
    return REFUSED_AT if max_jobs is None else EVERY_SLOT


def _is_accepting_now(worker: WorkerStatus, now: float) -> bool:
    return (
        is_heard(worker, now)
        and not worker.cordoned
        and not worker.draining
        and worker.load < _line_of(worker.max_jobs)
    )
