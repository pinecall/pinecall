"""A room kept under a fleet of no env's is let go at once, not swept until it ages out."""

import time
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinecall_runtime.fleet.models import Offer
from pinecall_runtime.fleet.repository import OfferRepository
from pinecall_runtime.fleet.service.offers import Offering
from pinecall_runtime.fleet.service.roster import Roster
from pinecall_runtime.wire.dispatch import Dispatch
from tests.conftest import needs_the_database

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
