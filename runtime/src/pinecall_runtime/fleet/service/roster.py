"""The roster of workers, one per fleet: who is up, what each holds, and whether a fleet is full."""

import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Literal

from pydantic import TypeAdapter

from pinecall_runtime.fleet.schemas import (
    FleetTotals,
    HeartbeatRequest,
    HeartbeatResponse,
    WorkerStatus,
)
from pinecall_runtime.kit.shared_state import Assigned, SharedState, newest
from pinecall_runtime.redis import LocalSignal, Signal
from pinecall_runtime.wire.feed import WorkerChanged

type WorkerState = Literal["gone", "cordoned", "draining", "accepting", "failing", "full"]

# LiveKit's line, the same on both of its sides: livekit-server's agent.DefaultTargetLoad
# (pkg/agent/config.go; a job is offered to a worker whose reported load is under it) and
# livekit-agents' load_threshold (the worker declines at or over it). A worker gated on CPU
# reports its share of the machine, which is that scale. A worker that counts its calls reports
# 0.7 times its calls over its slots to LiveKit (heartbeat.Load), so LiveKit's full is its last
# slot, and calls over slots to the gateway, full at 1.0: on 2026-10-02 it reported calls over
# slots to both, and LiveKit stopped at 0.7 of them while the gateway still counted seats free.
REFUSED_AT = 0.7
EVERY_SLOT = 1.0
OVERFLOW = "overflow"
HEARTBEAT_S = 5.0
# A worker silent this long is no longer capacity.
STALE_AFTER_S = 30.0
# A silent worker stays listed, as gone, this long.
FORGOTTEN_AFTER_S = 3600.0
# A worker up but bad: at least half the calls that ended in its last minute ended in an error,
# judged on four calls at least, or its callers waited over five seconds for first audio at the
# p95, over twenty turns at least. Set so they change nothing a healthy worker does.
FAILED_SHARE = 0.5
ENDED_TO_JUDGE = 4
SLOW_FIRST_AUDIO_S = 5.0
TURNS_TO_JUDGE = 20

# Every gateway says the heartbeats it heard and the cordons it set, once a heartbeat; each answers
# a heartbeat's `full` from totals at most this old, not by walking the fleet every time.
ROSTER_CHANNEL = "roster"
TOTALS_KEPT_S = 1.0
CORDONED = "cordoned"

type WorkerKey = tuple[str, str]


@dataclass(frozen=True)
class Share:
    """One gateway's share: the workers that beat on it lately, and the cordons it set."""

    seats: tuple[WorkerStatus, ...] = ()
    cordons: tuple[Assigned, ...] = ()


_SHARE: TypeAdapter[Share] = TypeAdapter(Share)


# In memory, on every gateway: each keeps the heartbeats that reached it and hears the others', so
# a worker beating on any gateway is counted on all of them. After a restart the next round of
# heartbeats, five seconds, rebuilds it; a cordon set on one gateway stands on all, the newest
# setting of a worker's cordon winning.
class Roster:
    """The workers of every fleet, by fleet and name, as their heartbeats say on any gateway."""

    def __init__(self, signal: Signal | None = None, on_change: Callable[[WorkerChanged], None] | None = None) -> None:
        """Nobody heard from yet; `on_change` hears each change of a worker this gateway hears."""
        self._on_change = on_change
        # Workers this gateway lost: told once as they go, once as they return.
        self._down: set[WorkerKey] = set()
        # Every gateway's workers, the newest heartbeat of each: what every read answers from.
        self.seats: dict[WorkerKey, WorkerStatus] = {}
        self.heard_here: dict[WorkerKey, WorkerStatus] = {}
        self.cordons: dict[WorkerKey, Assigned] = {}
        self.cordoned: dict[WorkerKey, str] = {}
        self.shared = SharedState(signal or LocalSignal(), ROSTER_CHANNEL, _SHARE, Share(), self._merge)
        self.shared.every_s = HEARTBEAT_S
        self.shared.gathered = self._gather
        self._totals: dict[str, tuple[float, FleetTotals]] = {}

    async def start(self) -> None:
        """Hear the other gateways' workers, and say this one's every heartbeat."""
        await self.shared.start()

    async def close(self) -> None:
        """Stop hearing and saying."""
        await self.shared.close()

    def report_heartbeat(self, beat: HeartbeatRequest, now: float) -> HeartbeatResponse:
        """Keep the heartbeat and answer the worker's standing; a cordon outlives heartbeats."""
        key: WorkerKey = (beat.fleet, beat.worker)
        cordoned = key in self.cordoned
        seat = WorkerStatus(**beat.model_dump(), cordoned=cordoned, seen_at=now)
        before, came_back = self.heard_here.get(key), key in self._down
        self._down.discard(key)
        self.heard_here[key] = seat
        self.seats[key] = seat
        if before is None or came_back or _shown(before) != _shown(seat):
            self._tell(seat, up=True)
        return HeartbeatResponse(cordoned=cordoned, full=self._kept_totals(beat.fleet, now).full)

    def cordon_worker(self, fleet: str, worker: str, *, on: bool = True) -> bool:
        """Cordon a worker, or take the cordon back; False for a name nobody has."""
        key: WorkerKey = (fleet, worker)
        if key not in self.seats:
            return False
        self.cordons[key] = Assigned(fleet, worker, CORDONED if on else None, time.time())
        self._merge()
        self.shared.put(self._gather())
        self._tell(self.seats[key], up=key not in self._down)
        return True

    def fleet_of_worker(self, worker: str) -> str | None:
        """The fleet a worker of that name beats for, or None when nobody has the name."""
        return next((fleet for fleet, name in self.seats if name == worker), None)

    def workers_of(self, fleet: str, now: float) -> list[WorkerStatus]:
        """A fleet's workers by last heartbeat, forgetting the ones silent for an hour."""
        for key, seat in list(self.seats.items()):
            if now - seat.seen_at > FORGOTTEN_AFTER_S:
                del self.seats[key]
        return sorted((seat for seat in self.seats.values() if seat.fleet == fleet), key=lambda seat: seat.seen_at)

    # A fleet nobody heard from is not full: a gateway with no worker yet refuses nobody.
    def totals_of(self, fleet: str, now: float) -> FleetTotals:
        """A fleet's workers heard from lately, summed."""
        up = [seat for seat in self.seats.values() if seat.fleet == fleet and heard_lately(seat, now)]
        accepting = len(accepting_of(up, now))
        return FleetTotals(
            fleet=fleet,
            workers=len(up),
            active=sum(seat.active for seat in up),
            seats=sum(seat.max_jobs or 0 for seat in up),
            free=sum(max(0, (seat.max_jobs or 0) - seat.active) for seat in up if seat.max_jobs),
            accepting=accepting,
            full=bool(up) and accepting == 0,
        )

    # A worker that stops beating sends nothing to say so: a silence past the line is found here,
    # on the tick tasks.py gives it.
    def forget_silent(self, now: float) -> None:
        """Say each worker this gateway heard and has not for too long, once."""
        for key, seat in list(self.heard_here.items()):
            if key not in self._down and not heard_lately(seat, now):
                self._down.add(key)
                self._tell(seat, up=False)

    def _tell(self, seat: WorkerStatus, *, up: bool) -> None:
        if self._on_change is not None:
            self._on_change(WorkerChanged(worker=seat.worker, fleet=seat.fleet, up=up, cordoned=seat.cordoned))

    def _kept_totals(self, fleet: str, now: float) -> FleetTotals:
        kept = self._totals.get(fleet)
        if kept is not None and 0 <= now - kept[0] < TOTALS_KEPT_S:
            return kept[1]
        totals = self.totals_of(fleet, now)
        self._totals[fleet] = (now, totals)
        return totals

    def _gather(self) -> Share:
        return Share(seats=tuple(self.heard_here.values()), cordons=tuple(self.cordons.values()))

    # Each worker's newest heartbeat, wherever it beat; each cordon's newest setting.
    def _merge(self) -> None:
        theirs = [heard.share for heard in self.shared.theirs.values()]
        self.cordoned = newest(self.cordons, (setting for share in theirs for setting in share.cordons))
        merged = dict(self.heard_here)
        for share in theirs:
            for seat in share.seats:
                known = merged.get((seat.fleet, seat.worker))
                if known is None or known.seen_at < seat.seen_at:
                    merged[(seat.fleet, seat.worker)] = seat
        self.seats = {key: seat.model_copy(update={"cordoned": key in self.cordoned}) for key, seat in merged.items()}


def heard_lately(seat: WorkerStatus, now: float) -> bool:
    """Whether the worker's last heartbeat is recent enough to count."""
    return now - seat.seen_at <= STALE_AFTER_S


def failing(seat: WorkerStatus) -> bool:
    """Whether the worker's last minute is past the line: its calls fail, or its callers wait."""
    ended, failed = seat.ended or 0, seat.failed or 0
    if ended >= ENDED_TO_JUDGE and failed / ended >= FAILED_SHARE:
        return True
    slow = seat.first_audio_p95_s
    return (seat.turns or 0) >= TURNS_TO_JUDGE and slow is not None and slow > SLOW_FIRST_AUDIO_S


# A failing worker is not counted while another of its fleet accepts and is not failing: the line
# never empties a fleet, so a box of one worker per env keeps counting its one.
def accepting_of(seats: Iterable[WorkerStatus], now: float) -> list[WorkerStatus]:
    """The fleet's workers counted as accepting: up and under the line, and not failing."""
    accepting = [seat for seat in seats if _accepting_now(seat, now)]
    sound = [seat for seat in accepting if not failing(seat)]
    return sound or accepting


def worker_state(seat: WorkerStatus, fleet: Sequence[WorkerStatus], now: float) -> WorkerState:
    """How the roster counts the worker among its fleet's: gone, cordoned, draining, and so on."""
    if not heard_lately(seat, now):
        return "gone"
    if seat.cordoned:
        return "cordoned"
    if seat.draining:
        return "draining"
    if seat in accepting_of(fleet, now):
        return "accepting"
    return "failing" if _accepting_now(seat, now) else "full"


# A worker registers with LiveKit under <fleet>/<worker>, the fleet's overflow under
# <fleet>/overflow: a dispatch reaches exactly the workers registered under its name.
def agent_name(fleet: str, worker: str) -> str:
    """The name a worker of a fleet is registered under with LiveKit."""
    return f"{fleet}/{worker}"


def overflow_name(fleet: str) -> str:
    """The name the fleet's overflow is registered under with LiveKit."""
    return agent_name(fleet, OVERFLOW)


def _refused_at(max_jobs: int | None) -> float:
    return REFUSED_AT if max_jobs is None else EVERY_SLOT


def _accepting_now(seat: WorkerStatus, now: float) -> bool:
    return (
        heard_lately(seat, now) and not seat.cordoned and not seat.draining and seat.load < _refused_at(seat.max_jobs)
    )


# What a screen of the fleet shows of a worker: a heartbeat that changes none of it says nothing.
# The load is read in tenths, the bar's own resolution: a CPU worker's share moves every beat.
def _shown(seat: WorkerStatus) -> tuple[object, ...]:
    return (seat.active, seat.max_jobs, round(seat.load, 1), seat.draining, seat.cordoned, failing(seat))
