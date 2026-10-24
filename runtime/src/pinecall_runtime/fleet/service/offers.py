"""Who takes a call: offered to a worker the gateway chose, then another, then the overflow."""

import logging
import time
from collections.abc import Collection, Mapping
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinecall_runtime.fleet.models import Offer
from pinecall_runtime.fleet.repository import OfferRepository
from pinecall_runtime.fleet.schemas import WorkerStatus
from pinecall_runtime.fleet.service import envs, rooms
from pinecall_runtime.fleet.service.roster import REFUSED_AT, Roster, accepting_of, overflow_name
from pinecall_runtime.kit.loops import survived
from pinecall_runtime.livekit import Servers
from pinecall_runtime.wire.dispatch import Dispatch

logger = logging.getLogger(__name__)

# LiveKit waits 10 s on a worker that does not answer before it gives a job up; a live worker opens
# its call in about 2 s. A room no worker opened 12 s after its offer is offered to another.
OFFERED_AGAIN_AFTER_S = 12.0

# Three offers, then the overflow's sentence: 36 s is the longest a caller waits on our account.
OFFERS = 3
# The longest from an offer to an agent in the room: every offer, and the overflow joining after them.
AN_AGENT_JOINS_WITHIN_S = OFFERS * OFFERED_AGAIN_AFTER_S + 10.0

# Two heartbeats and a margin: a worker unheard this long may be gone, and LiveKit would keep a
# dead one for 15 minutes; it is not offered a call until it is heard again.
HEARD_WITHIN_S = 12.0

# A fleet none of whose workers was heard is one the gateway knows nothing of yet (it just
# started): the room waits for the next sweep, up to as long as a worker takes to be heard.
WAITS_FOR_A_WORKER_S = HEARD_WITHIN_S

# The rooms counted as waiting for a worker: the ones a caller joined in the last ten minutes.
WAITING_COUNTED_S = 600.0

# Every room is done with by its third offer and a sweep after it: one kept a minute is a room no
# gateway is sweeping.
UNSWEPT_AFTER_S = 60.0

# Past any offer: a caller who waited this long has hung up, and the SIP leg is gone.
FORGOTTEN_AFTER_S = 120.0

SWEPT_AT_MOST = 100


@dataclass(frozen=True, slots=True)
class Target:
    """Whom a room goes to now, and why, so the log says it; nobody while no worker was heard."""

    agent: str | None
    why: str


# What a process holds to send a call to a worker: the offers table, each env's LiveKit, and the
# fleet's workers as their heartbeats say. Every endpoint that sends a call into a room goes
# through it. A room lives on the LiveKit of its fleet's env, which the fleets setting says. Each
# write is its own short transaction, as the sweep on another gateway must see it at once.
@dataclass(frozen=True)
class Offering:
    """The gateway's dispatcher: a room offered to the worker it chose, by the worker's name."""

    sessions: async_sessionmaker[AsyncSession]
    servers: Servers
    roster: Roster

    async def offer(self, room: str, fleet: str, dispatch: Dispatch) -> str | None:
        """Keep the room and offer it; the name it went to, or None if kept already or not yet."""
        carried = dispatch.dump()
        now = time.time()
        async with self.sessions.begin() as session:
            if not await OfferRepository(session).open(room, fleet, carried, now):
                return None
        return await self.offer_again(
            Offer(room=room, fleet=fleet, dispatch=carried, seen_at=now, worker=None, offers=0)
        )

    # A fleet no env's calls go to (the operator renamed it, or the room was kept by a dispatch
    # that names no fleet) has no LiveKit to hold the room and no worker to take it: kept, the room
    # would be swept every few seconds until it aged out, saying so each time (2026-10-21: one
    # room, two gateways, eighty warnings).
    async def offer_again(self, offer: Offer) -> str | None:
        """Offer the room to the worker it should go to now; the name, or None if not offered."""
        now = time.time()
        async with self.sessions.begin() as session:
            env = envs.env_of_fleet(await envs.fleets(session), offer.fleet)
            if env is None:
                await OfferRepository(session).forget(offer.room)
                logger.warning(
                    "room %s: fleet %r is no env's, so no LiveKit holds its room; let go", offer.room, offer.fleet
                )
                return None
            target = await self._target(session, offer, now)
            if target.agent is None:
                logger.info("room %s: %s; offered at the next sweep", offer.room, target.why)
                return None
            if not await OfferRepository(session).claim(offer.room, offer.offers, target.agent, now):
                return None
        await rooms.dispatch_into(self.servers[env], offer.room, target.agent, Dispatch.parse(offer.dispatch))
        if target.agent == overflow_name(offer.fleet):
            await self.forget(offer.room)
            logger.warning("room %s: %s; the overflow says the sentence", offer.room, target.why)
        elif offer.offers > 0:
            logger.warning(
                "room %s: no worker opened it in %.0f s; offered to %s (offer %d): %s",
                offer.room,
                OFFERED_AGAIN_AFTER_S,
                target.agent,
                offer.offers + 1,
                target.why,
            )
        else:
            logger.info("room %s: offered to %s: %s", offer.room, target.agent, target.why)
        return target.agent

    # A worker's heartbeat says its seats; a gateway that heard no worker yet cannot say the fleet is full.
    async def has_a_seat(self, fleet: str) -> bool:
        """Whether a call offered now would find a worker with a seat; True while no worker was heard."""
        now = time.time()
        seats = self.roster.workers_of(fleet, now)
        if not any_heard(seats, now):
            return True
        async with self.sessions.begin() as session:
            flying = await OfferRepository(session).in_flight(now - OFFERED_AGAIN_AFTER_S)
        return choose_worker(seats, flying, now) is not None

    async def forget(self, room: str) -> None:
        """The room is done with: its call opened, the overflow sent, or the room gone."""
        async with self.sessions.begin() as session:
            await OfferRepository(session).forget(room)

    async def sweep(self) -> list[str]:
        """Offer again every room nobody opened in time; the rooms offered."""
        now = time.time()
        async with self.sessions.begin() as session:
            offers = OfferRepository(session)
            await offers.age_out(now - FORGOTTEN_AFTER_S)
            due = list(await offers.due(now - OFFERED_AGAIN_AFTER_S, SWEPT_AT_MOST))
        offered: list[str] = []
        # Oldest first: a room that cannot be offered is said and left, or no room behind it ever would be.
        for offer in due:
            with survived("offering a room again", offer.room):
                if await self.offer_again(offer) is not None:
                    offered.append(offer.room)
        return offered

    async def waiting(self, now: float) -> dict[str, int]:
        """Each fleet's rooms with a caller that no worker opened yet."""
        async with self.sessions.begin() as session:
            return await OfferRepository(session).waiting(now - WAITING_COUNTED_S)

    async def examine(self, now: float) -> str | None:
        """What the doctor says of the offers: the rooms kept past every offer, or None."""
        async with self.sessions.begin() as session:
            kept = await OfferRepository(session).count_kept_since(now - UNSWEPT_AFTER_S)
        return (
            f"{kept} rooms a caller joined over a minute ago were never let go: no gateway sweeps them"
            if kept
            else None
        )

    # The worker chosen; the overflow when the offers ran out or the workers heard have no seat;
    # nobody while no worker of the fleet was heard yet.
    async def _target(self, session: AsyncSession, offer: Offer, now: float) -> Target:
        if offer.offers >= OFFERS:
            return Target(overflow_name(offer.fleet), f"no worker opened it in {OFFERS} offers")
        flying = await OfferRepository(session).in_flight(now - OFFERED_AGAIN_AFTER_S)
        tried = () if offer.worker is None else (offer.worker,)
        seats = self.roster.workers_of(offer.fleet, now)
        seat = choose_worker(seats, flying, now, not_these=tried)
        if seat is not None and seat.agent_name is not None:
            return Target(
                seat.agent_name, f"{free_seats(seat, flying)} seats free, heard {now - seat.seen_at:.0f} s ago"
            )
        if not any_heard(seats, now) and now - offer.seen_at < WAITS_FOR_A_WORKER_S:
            return Target(None, f"no worker of the fleet heard in {HEARD_WITHIN_S:.0f} s")
        return Target(overflow_name(offer.fleet), "no worker of the fleet has a seat")


def choose_worker(
    seats: Collection[WorkerStatus], in_flight: Mapping[str, int], now: float, not_these: Collection[str] = ()
) -> WorkerStatus | None:
    """The worker to offer a call to, or None when no worker of the fleet has a seat."""
    candidates = [
        seat
        for seat in accepting_of(seats, now)
        if seat.agent_name is not None
        and seat.agent_name not in not_these
        and now - seat.seen_at <= HEARD_WITHIN_S
        and free_seats(seat, in_flight) > 0
    ]
    return max(candidates, key=lambda seat: (free_seats(seat, in_flight), -seat.load), default=None)


# A gateway that just started rebuilds its roster from the next heartbeats, five seconds: until a
# worker of the fleet is heard, nobody can say the fleet is full.
def any_heard(seats: Collection[WorkerStatus], now: float) -> bool:
    """Whether any worker of the fleet was heard lately, whatever it is doing."""
    return any(now - seat.seen_at <= HEARD_WITHIN_S for seat in seats)


# A worker gated on its CPU has no count of seats: one call at a time is offered to it, under
# LiveKit's line.
def free_seats(seat: WorkerStatus, in_flight: Mapping[str, int]) -> int:
    """The seats a worker has free, its calls and the ones offered to it not yet opened taken."""
    offered = in_flight.get(seat.agent_name or "", 0)
    if seat.max_jobs is None:
        return 1 if seat.load < REFUSED_AT and offered == 0 else 0
    return seat.max_jobs - seat.active - offered
