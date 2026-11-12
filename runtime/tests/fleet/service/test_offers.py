"""The offers: a room of no env's fleet is let go at once, and the sweep goes on past a room it cannot offer."""

import time
from uuid import uuid4

import pytest
from livekit import api
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.enums import Env
from runtime.fleet.models import Offer
from runtime.fleet.repository import OfferRepository
from runtime.fleet.schemas import WorkerStatus
from runtime.fleet.service.dispatches import agent_name
from runtime.fleet.service.envs import PRODUCTION, SANDBOX
from runtime.fleet.service.offers import OFFERED_AGAIN_AFTER_S, Offering
from runtime.fleet.service.roster import Roster
from runtime.wire.dispatch import Dispatch
from tests.conftest import needs_the_database
from tests.fakes.livekit import per_world

pytestmark = needs_the_database


# On 2026-10-21 a simulated call's room was kept under LiveKit's unnamed dispatch once its agent
# left, and two gateways warned of it eighty times in the two minutes before it aged out.
async def test_a_room_of_a_fleet_no_env_owns_is_let_go_at_its_next_offer(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    offering = Offering(sessions, servers={}, roster=Roster())
    room = f"call_{uuid4().hex}"
    now = time.time()
    async with sessions.begin() as session:
        assert await OfferRepository(session).open(room, "", Dispatch(agent="recepcion").dump(), now)
    kept = Offer(room=room, fleet="", dispatch=Dispatch(agent="recepcion").dump(), seen_at=now, worker=None, offers=0)
    assert await offering.offer_again(kept) is None
    assert await _kept(sessions, room) is None


async def _kept(sessions: async_sessionmaker[AsyncSession], room: str) -> Offer | None:
    async with sessions.begin() as session:
        return await session.get(Offer, room)


# The sweep reads the rooms oldest first: one it could not offer again, and said nothing of, ended
# the sweep at it on every pass, and no room behind it was offered again.
async def test_a_room_that_cannot_be_offered_again_is_said_and_the_rooms_behind_it_are_offered(
    sessions: async_sessionmaker[AsyncSession], caplog: pytest.LogCaptureFixture
) -> None:
    bad, good = f"call_bad_{uuid4().hex}", f"call_good_{uuid4().hex}"
    # Due to be offered again, the bad one the older, in the sandbox, whose LiveKit refuses every dispatch.
    due = time.time() - OFFERED_AGAIN_AFTER_S - 1
    async with sessions.begin() as session:
        offers = OfferRepository(session)
        assert await offers.open(bad, SANDBOX, Dispatch(agent="recepcion").dump(), due - 1)
        assert await offers.open(good, PRODUCTION, Dispatch(agent="recepcion").dump(), due)
    roster = Roster()
    roster.workers[(SANDBOX, "w1")] = a_worker("w1", active=0, fleet=SANDBOX)
    roster.workers[(PRODUCTION, "w2")] = a_worker("w2", active=0, fleet=PRODUCTION)
    servers = per_world()
    servers[Env.sandbox].dispatcher.refusal = api.TwirpError("unavailable", "the SFU is restarting", status=503)
    try:
        offered = await Offering(sessions, servers=servers, roster=roster).sweep()
    finally:
        for server in servers.values():
            await server.aclose()
    assert good in offered and bad not in offered
    assert f"offering a room again failed on {bad}" in caplog.text


def a_worker(
    name: str, *, active: int, max_jobs: int = 2, seen_at: float | None = None, fleet: str = "sandbox"
) -> WorkerStatus:
    """A worker of the fleet, the sandbox's unless named, as its last heartbeat left it."""
    return WorkerStatus(
        fleet=fleet,
        worker=name,
        agent_name=agent_name(fleet, name),
        active=active,
        max_jobs=max_jobs,
        load=0.1,
        draining=False,
        cordoned=False,
        seen_at=time.time() if seen_at is None else seen_at,
    )


# G S5 (2026-10-23): a spoken simulation placed with both of the sandbox's seats taken waited through the
# offers, gave up before the overflow joined, and said "no agent joined in 40s: is the env's fleet up?".
async def test_a_fleet_has_a_slot_while_a_worker_has_one_and_is_said_full_when_none_has(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    roster = Roster()
    offering = Offering(sessions, servers={}, roster=roster)
    assert await offering.has_a_slot("sandbox"), "a fleet nobody heard yet is not said to be full"
    roster.workers[("sandbox", "w1")] = a_worker("w1", active=2)
    assert not await offering.has_a_slot("sandbox")
    roster.workers[("sandbox", "w2")] = a_worker("w2", active=1)
    assert await offering.has_a_slot("sandbox")
    roster.workers[("sandbox", "w2")] = a_worker("w2", active=2)
    assert not await offering.has_a_slot("sandbox")
