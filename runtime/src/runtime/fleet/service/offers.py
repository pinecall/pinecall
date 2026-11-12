"""Who takes a call: offered to a worker the gateway chose, then another, then the overflow."""

import logging
import time
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.fleet.models import Offer
from runtime.fleet.repository import OfferRepository
from runtime.fleet.service import dispatches, envs, slots
from runtime.fleet.service.roster import Roster
from runtime.kit.loops import survive
from runtime.livekit import Servers
from runtime.wire.dispatch import Dispatch

logger = logging.getLogger(__name__)

# LiveKit waits 10 s on a worker that does not answer before it gives a job up; a live worker opens
# its call in about 2 s. A room no worker opened 12 s after its offer is offered to another.
OFFERED_AGAIN_AFTER_S = 12.0

# Three offers, then the overflow's sentence: 36 s is the longest a caller waits on our account.
OFFERS = 3
# The longest from an offer to an agent in the room: every offer, and the overflow joining after them.
AN_AGENT_JOINS_WITHIN_S = OFFERS * OFFERED_AGAIN_AFTER_S + 10.0

# A fleet none of whose workers was heard is one the gateway knows nothing of yet (it just
# started): the room waits for the next sweep, up to as long as a worker takes to be heard.
WAITS_FOR_A_WORKER_S = slots.OFFERABLE_WITHIN_S

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
        async with self.sessions.begin() as session:
            kept = await OfferRepository(session).open(room, fleet, dispatch.dump(), time.time())
        return None if kept is None else await self.offer_again(kept)

    # A fleet no env's calls go to (the operator renamed it, or the room was kept by a dispatch
    # that names no fleet) has no LiveKit to hold the room and no worker to take it: kept, the room
    # would be swept every few seconds until it aged out, saying so each time (2026-10-21: one
    # room, two gateways, eighty warnings).
    async def offer_again(self, offer: Offer) -> str | None:
        """Offer the room to the worker it should go to now; the name, or None if not offered."""
        now = time.time()
        async with self.sessions.begin() as session:
            env = envs.env_of_fleet(await envs.get_fleets(session), offer.fleet)
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
        await dispatches.dispatch_into(self.servers[env], offer.room, target.agent, Dispatch.parse(offer.dispatch))
        if target.agent == dispatches.overflow_name(offer.fleet):
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

    async def has_a_slot(self, fleet: str) -> bool:
        """Whether a call offered now would find a worker with a slot; True while no worker was heard."""
        now = time.time()
        async with self.sessions.begin() as session:
            flying = await count_in_flight(session, now)
        return slots.has_a_slot(self.roster.workers_of(fleet, now), flying, now)

    async def forget(self, room: str) -> None:
        """The room is done with: its call opened, the overflow sent, or the room gone."""
        async with self.sessions.begin() as session:
            await OfferRepository(session).forget(room)

    async def sweep(self) -> list[str]:
        """Offer again every room nobody opened in time; the rooms offered."""
        now = time.time()
        async with self.sessions.begin() as session:
            offers = OfferRepository(session)
            await offers.forget_older_than(now - FORGOTTEN_AFTER_S)
            due = list(await offers.list_due(now - OFFERED_AGAIN_AFTER_S, SWEPT_AT_MOST))
        offered: list[str] = []
        # Oldest first: a room that cannot be offered is said and left, or no room behind it ever would be.
        for offer in due:
            with survive("offering a room again", offer.room):
                if await self.offer_again(offer) is not None:
                    offered.append(offer.room)
        return offered

    # The worker chosen; the overflow when the offers ran out or the workers heard have no slot;
    # nobody while no worker of the fleet was heard yet.
    async def _target(self, session: AsyncSession, offer: Offer, now: float) -> Target:
        if offer.offers >= OFFERS:
            return Target(dispatches.overflow_name(offer.fleet), f"no worker opened it in {OFFERS} offers")
        flying = await count_in_flight(session, now)
        tried = () if offer.worker is None else (offer.worker,)
        workers = self.roster.workers_of(offer.fleet, now)
        chosen = slots.choose_worker(workers, flying, now, not_these=tried)
        if chosen is not None and chosen.agent_name is not None:
            free = slots.free_slots(chosen, flying)
            return Target(chosen.agent_name, f"{free} slots free, heard {now - chosen.seen_at:.0f} s ago")
        if not slots.is_any_heard(workers, now) and now - offer.seen_at < WAITS_FOR_A_WORKER_S:
            return Target(None, f"no worker of the fleet heard in {slots.OFFERABLE_WITHIN_S:.0f} s")
        return Target(dispatches.overflow_name(offer.fleet), "no worker of the fleet has a slot")


# The two reads of the table that need neither LiveKit nor the roster: until 2026-11 they were the
# dispatcher's methods, and the doctor built a dispatcher on an empty roster to ask one of them.
async def count_waiting(session: AsyncSession, now: float) -> dict[str, int]:
    """Each fleet's rooms with a caller that no worker opened yet."""
    return await OfferRepository(session).count_waiting(now - WAITING_COUNTED_S)


async def count_in_flight(session: AsyncSession, now: float) -> dict[str, int]:
    """Each worker's rooms offered to it lately that it has not opened: the slots those offers take."""
    return await OfferRepository(session).count_in_flight(now - OFFERED_AGAIN_AFTER_S)


async def examine(session: AsyncSession, now: float) -> str | None:
    """What the doctor says of the offers: the rooms kept past every offer, or None."""
    kept = await OfferRepository(session).count_older_than(now - UNSWEPT_AFTER_S)
    return f"{kept} rooms a caller joined over a minute ago were never let go: no gateway sweeps them" if kept else None
