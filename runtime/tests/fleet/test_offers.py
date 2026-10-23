"""The offers: a room of no env's fleet is let go at once, and the sweep goes on past a room it cannot offer."""

import time
from uuid import uuid4

import pytest
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


def an_offer(room: str, seen_at: float) -> Offer:
    """A room kept under a fleet, never offered."""
    return Offer(
        room=room, fleet="pinecall", dispatch=Dispatch(agent="recepcion").dump(), seen_at=seen_at, worker=None, offers=0
    )


# The sweep reads the rooms oldest first: one it could not offer again, and said nothing of, ended
# the sweep at it on every pass, and no room behind it was offered again.
async def test_a_room_that_cannot_be_offered_again_is_said_and_the_rooms_behind_it_are_offered(
    monkeypatch: pytest.MonkeyPatch,
    sessions: async_sessionmaker[AsyncSession],
    caplog: pytest.LogCaptureFixture,
) -> None:
    bad, good = an_offer("call_bad", 1.0), an_offer("call_good", 2.0)

    async def due(_repository: OfferRepository, _before: float, _most: int) -> list[Offer]:
        return [bad, good]

    async def offer_again(_offering: Offering, offer: Offer) -> str | None:
        if offer.room == bad.room:
            raise ValueError("1 validation error for Dispatch")
        return "a worker"

    monkeypatch.setattr(OfferRepository, "due", due)
    monkeypatch.setattr(Offering, "offer_again", offer_again)
    assert await Offering(sessions, servers={}, roster=Roster()).sweep() == ["call_good"]
    assert "offering a room again failed on call_bad" in caplog.text
