"""The roster of workers, one per fleet: who was heard, on which gateway, and who is cordoned."""

import time
from collections.abc import Callable

from runtime.exceptions import NotFound
from runtime.fleet.service import slots
from runtime.kit.loops import survive
from runtime.shared_state import Assigned, SharedState, newest
from runtime.signal import LocalSignal, Signal
from runtime.wire.feed import WorkerChanged
from runtime.wire.signal import Assignment, RosterShare, WorkerStatus
from runtime.wire.worker import HeartbeatRequest, HeartbeatResponse

# Every gateway says the heartbeats it heard and the cordons it set, once a heartbeat.
ROSTER_CHANNEL = "roster"
CORDONED = "cordoned"

type WorkerKey = tuple[str, str]


class NoSuchWorker(NotFound):
    """A cordon names a worker nobody heard from."""

    def __init__(self, worker: str) -> None:
        super().__init__(f"no worker {worker} was heard from: the roster lists the ones that were")


# In memory, on every gateway: each keeps the heartbeats that reached it and hears the others', so
# a worker beating on any gateway is counted on all of them. After a restart the next round of
# heartbeats, five seconds, rebuilds it; a cordon set on one gateway stands on all, the newest
# setting of a worker's cordon winning. What the roster makes of a worker (heard, accepting, a
# slot free) is `slots`' to say: the roster keeps who was heard and tells the others.
class Roster:
    """The workers of every fleet, by fleet and name, as their heartbeats say on any gateway."""

    def __init__(self, signal: Signal | None = None, on_change: Callable[[WorkerChanged], None] | None = None) -> None:
        """Nobody heard from yet; `on_change` hears each change of a worker this gateway hears."""
        self._on_change = on_change
        # Workers this gateway lost: told once as they go, once as they return.
        self._down: set[WorkerKey] = set()
        # Every gateway's workers, the newest heartbeat of each: what every read answers from.
        self.workers: dict[WorkerKey, WorkerStatus] = {}
        self.heard_here: dict[WorkerKey, WorkerStatus] = {}
        self.cordons: dict[WorkerKey, Assigned] = {}
        self.cordoned: dict[WorkerKey, str] = {}
        self.shared = SharedState(
            signal or LocalSignal(),
            ROSTER_CHANNEL,
            load=RosterShare.model_validate,
            dump=RosterShare.model_dump,
            empty=RosterShare(),
            on_change=self._merge,
            every_s=slots.HEARTBEAT_S,
            gathered=self._gather,
        )

    async def start(self) -> None:
        """Hear the other gateways' workers, and say this one's every heartbeat."""
        await self.shared.start()

    async def close(self) -> None:
        """Stop hearing and saying."""
        await self.shared.close()

    def report_heartbeat(self, beat: HeartbeatRequest, now: float) -> HeartbeatResponse:
        """Keep the heartbeat and answer the worker's standing; a cordon outlives heartbeats."""
        key: WorkerKey = (beat.fleet, beat.worker)
        worker = WorkerStatus(**beat.model_dump(), cordoned=key in self.cordoned, seen_at=now)
        before, came_back = self.heard_here.get(key), key in self._down
        self._down.discard(key)
        self.heard_here[key] = worker
        self.workers[key] = worker
        if before is None or came_back or _display_of(before) != _display_of(worker):
            self._tell(worker, up=True)
        full = slots.accepts_nobody(self.workers_of(beat.fleet, now), now)
        return HeartbeatResponse(cordoned=worker.cordoned, full=full)

    # A cordon is told on the worker's next heartbeat: it takes no new call, finishes, and leaves.
    def cordon(self, worker: str, fleet: str | None = None) -> None:
        """Cordon a worker of a fleet; the fleet is found by the worker's name when not named."""
        self._set_cordon(worker, fleet, CORDONED)

    def uncordon(self, worker: str, fleet: str | None = None) -> None:
        """Take a worker's cordon back, when it has not left yet."""
        self._set_cordon(worker, fleet, None)

    def fleet_of_worker(self, worker: str) -> str | None:
        """The fleet a worker of that name beats for, or None when nobody has the name."""
        return next((fleet for fleet, name in self.workers if name == worker), None)

    # A read, and nothing else: until 2026-11 it also deleted the workers silent for an hour, from
    # five callers, and the next word of another gateway put them back.
    def workers_of(self, fleet: str, now: float) -> list[WorkerStatus]:
        """A fleet's workers by last heartbeat, the ones silent for an hour left out."""
        listed = [
            worker
            for worker in self.workers.values()
            if worker.fleet == fleet and slots.is_heard(worker, now, slots.FORGOTTEN_AFTER_S)
        ]
        return sorted(listed, key=lambda worker: worker.seen_at)

    # A worker that stops beating sends nothing to say so: a silence past the line is found here,
    # on the tick tasks.py gives it. The same tick lets go of what is spent. Until 2026-11 nothing
    # did: every worker ever heard stayed in `heard_here`, and so in the share this gateway says
    # whole every heartbeat, until the gateway restarted; with scaled workers named by their pod,
    # that is every pod there ever was.
    def forget_silent(self, now: float) -> None:
        """Say each worker this gateway heard and has not for too long, once; forget the ones silent for an hour."""
        for key, worker in list(self.heard_here.items()):
            if not slots.is_heard(worker, now, slots.FORGOTTEN_AFTER_S):
                del self.heard_here[key]
                self._down.discard(key)
            elif key not in self._down and not slots.is_heard(worker, now):
                self._down.add(key)
                with survive("saying a worker is silent", worker.worker):
                    self._tell(worker, up=False)
        for key, cordon in list(self.cordons.items()):
            if self._is_spent(cordon, self.workers.get(key), now):
                del self.cordons[key]
        self._merge()

    def _set_cordon(self, worker: str, fleet: str | None, holder: str | None) -> None:
        key: WorkerKey = (fleet or self.fleet_of_worker(worker) or "", worker)
        if key not in self.workers:
            raise NoSuchWorker(worker)
        self.cordons[key] = Assigned(key[0], worker, holder, time.time())
        self._merge()
        self.shared.put(self._gather())
        self._tell(self.workers[key], up=key not in self._down)

    # A cordon is spent once its worker left: set over an hour ago, on a worker nobody heard in the hour.
    def _is_spent(self, cordon: Assigned, worker: WorkerStatus | None, now: float) -> bool:
        silent = worker is None or not slots.is_heard(worker, now, slots.FORGOTTEN_AFTER_S)
        return silent and now - cordon.at > slots.FORGOTTEN_AFTER_S

    def _tell(self, worker: WorkerStatus, *, up: bool) -> None:
        if self._on_change is not None:
            self._on_change(WorkerChanged(worker=worker.worker, fleet=worker.fleet, up=up, cordoned=worker.cordoned))

    def _gather(self) -> RosterShare:
        return RosterShare(
            workers=tuple(self.heard_here.values()),
            cordons=tuple(Assignment.model_validate(cordon) for cordon in self.cordons.values()),
        )

    # Each worker's newest heartbeat, wherever it beat; each cordon's newest setting.
    def _merge(self) -> None:
        theirs = [heard.share for heard in self.shared.theirs.values()]
        told = (Assigned(**cordon.model_dump()) for share in theirs for cordon in share.cordons)
        self.cordoned = newest(self.cordons, told)
        merged = dict(self.heard_here)
        for share in theirs:
            for worker in share.workers:
                known = merged.get((worker.fleet, worker.worker))
                if known is None or known.seen_at < worker.seen_at:
                    merged[(worker.fleet, worker.worker)] = worker
        self.workers = {
            key: worker.model_copy(update={"cordoned": key in self.cordoned}) for key, worker in merged.items()
        }


# What a screen of the fleet shows of a worker: a heartbeat that changes none of it says nothing.
# The load is read in tenths, the bar's own resolution: a CPU worker's share moves every beat.
def _display_of(worker: WorkerStatus) -> tuple[object, ...]:
    return (
        worker.active,
        worker.max_jobs,
        round(worker.load, 1),
        worker.draining,
        worker.cordoned,
        slots.is_failing(worker),
    )
