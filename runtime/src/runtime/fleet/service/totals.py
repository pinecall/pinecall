"""A fleet summed over the workers heard from: its calls, its slots, whether one is free, and the rooms waiting."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.fleet.service import envs, offers, slots
from runtime.fleet.service.roster import Roster
from runtime.wire.signal import WorkerStatus


@dataclass(frozen=True, slots=True)
class FleetTotals:
    """One fleet over the workers heard from lately."""

    fleet: str
    workers: int
    active: int
    slots: int
    free: int
    accepting: int
    full: bool
    # Rooms with a caller that no worker opened yet, offered by the gateway.
    waiting: int = 0


@dataclass(frozen=True, slots=True)
class Listing:
    """The box's time, every worker heard from, and each fleet summed."""

    now: float
    stale_after_s: float
    workers: list[WorkerStatus]
    totals: list[FleetTotals]


# Full and free are `slots`' own answers, the ones the dispatcher offers a call by. Until 2026-11
# the totals had a count of their own (a worker heard for 30 s, its load, no offer in flight), so
# a fleet could read as having room here while its next caller was sent the overflow's sentence.
def sum_fleet(
    fleet: str, workers: Sequence[WorkerStatus], in_flight: Mapping[str, int], waiting: int, now: float
) -> FleetTotals:
    """A fleet's workers heard from lately, summed; a fleet nobody heard from is not full."""
    up = [worker for worker in workers if slots.is_heard(worker, now)]
    return FleetTotals(
        fleet=fleet,
        workers=len(up),
        active=sum(worker.active for worker in up),
        slots=sum(worker.max_jobs or 0 for worker in up),
        free=sum(max(0, slots.free_slots(worker, in_flight)) for worker in up),
        accepting=len(slots.accepting_of(up, now)),
        full=not slots.has_a_slot(workers, in_flight, now),
        waiting=waiting,
    )


async def totals_of(session: AsyncSession, roster: Roster, fleet: str, now: float) -> FleetTotals:
    """One fleet summed now, the offers in flight and the rooms waiting read from the table."""
    in_flight = await offers.count_in_flight(session, now)
    waiting = await offers.count_waiting(session, now)
    return sum_fleet(fleet, roster.workers_of(fleet, now), in_flight, waiting.get(fleet, 0), now)


async def list_fleets(session: AsyncSession, roster: Roster, now: float) -> Listing:
    """Every worker heard from, of both envs' fleets, and each fleet summed over the ones up."""
    named = await envs.get_fleets(session)
    both = list(dict.fromkeys((named.production, named.sandbox)))
    in_flight = await offers.count_in_flight(session, now)
    waiting = await offers.count_waiting(session, now)
    of_each = {fleet: roster.workers_of(fleet, now) for fleet in both}
    return Listing(
        now=now,
        stale_after_s=slots.STALE_AFTER_S,
        workers=[worker for fleet in both for worker in of_each[fleet]],
        totals=[sum_fleet(fleet, of_each[fleet], in_flight, waiting.get(fleet, 0), now) for fleet in both],
    )
