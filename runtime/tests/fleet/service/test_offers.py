"""The offers: a room of no env's fleet is let go, the sweep passes a room it cannot offer, a seat is taken once."""

import time
from uuid import uuid4

import pytest
from livekit import api
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.enums import Env
from runtime.fleet.models import Offer
from runtime.fleet.repository import OfferRepository
from runtime.fleet.schemas import WorkerStatus
from runtime.fleet.service import slots
from runtime.fleet.service.dispatches import agent_name, overflow_name
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


# 2026-11-16: a call handed on three seconds after its worker's pod was deleted was offered to that
# pod, heard six seconds before and with every seat free, and its caller waited twelve more seconds.
# The roster is told the worker is gone, so a room that has nothing to do with it is not offered to it either.
async def test_a_room_its_worker_left_is_offered_to_another_worker_even_with_fewer_seats_free(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    servers, roster = per_world(), Roster()
    offering = Offering(sessions, servers=servers, roster=roster)
    roster.workers[(SANDBOX, "gone")] = a_worker("gone", active=0, max_jobs=32, fleet=SANDBOX)
    roster.workers[(SANDBOX, "busy")] = a_worker("busy", active=1, max_jobs=3, fleet=SANDBOX)
    room, another = f"room_{uuid4().hex}", f"room_{uuid4().hex}"
    try:
        gone = agent_name(SANDBOX, "gone")
        assert await offering.offer(room, SANDBOX, Dispatch(agent="recepcion"), left_by=gone) == agent_name(
            SANDBOX, "busy"
        )
        assert await offering.offer(another, SANDBOX, Dispatch(agent="recepcion")) == agent_name(SANDBOX, "busy")
    finally:
        await offering.forget(room)
        await offering.forget(another)
        for server in servers.values():
            await server.aclose()


# 2026-11-24: sixty simulated calls placed on a sandbox of eight seats. Every caller waiting asked
# `has_a_slot` at the same moment, saw the one seat that had freed, and offered its room: the ones past
# the seat were answered by the overflow's sentence, twenty-nine of them, as calls of the comparison.
async def test_two_callers_that_ask_for_the_one_seat_together_are_not_both_seated(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    servers, roster = per_world(), Roster()
    offering = Offering(sessions, servers=servers, roster=roster)
    only = f"w_{uuid4().hex}"
    roster.workers[(SANDBOX, only)] = a_worker(only, active=1, max_jobs=2, fleet=SANDBOX)
    first, second = f"room_{uuid4().hex}", f"room_{uuid4().hex}"
    try:
        seat = await offering.take_seat(first, SANDBOX, Dispatch(agent="recepcion"))
        assert seat is not None and seat.worker == agent_name(SANDBOX, only)
        assert await offering.take_seat(second, SANDBOX, Dispatch(agent="recepcion")) is None
        assert await _kept(sessions, second) is None, "a caller that got no seat keeps no room: it asks again"
        kept = await _kept(sessions, first)
        assert kept is not None and kept.worker == agent_name(SANDBOX, only), "taken before the room is rung"
        await offering.ring(seat, Dispatch(agent="recepcion"))
    finally:
        await offering.forget(first)
        for server in servers.values():
            await server.aclose()


# The worker's heartbeat says its calls every five seconds: between a call's opening and that beat the
# offer was gone and the heartbeat still said the slot free, so the next caller in the queue took it.
async def test_a_seat_stays_taken_from_its_calls_opening_until_its_worker_says_the_call(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    servers, roster = per_world(), Roster()
    offering = Offering(sessions, servers=servers, roster=roster)
    heard, only = time.time() - 3, f"w_{uuid4().hex}"
    roster.workers[(SANDBOX, only)] = a_worker(only, active=1, max_jobs=2, seen_at=heard, fleet=SANDBOX)
    room = f"room_{uuid4().hex}"
    try:
        assert await offering.take_seat(room, SANDBOX, Dispatch(agent="recepcion")) is not None
        await offering.say_opened(room)
        assert not await offering.has_a_slot(SANDBOX), "opened since the worker last beat: the seat is its call's"
        # The worker beats, its call counted: the offer takes nothing more, and the slot is not taken twice.
        roster.workers[(SANDBOX, only)] = a_worker(only, active=2, max_jobs=3, fleet=SANDBOX)
        assert await offering.has_a_slot(SANDBOX)
    finally:
        await offering.forget(room)
        for server in servers.values():
            await server.aclose()


# A room is offered again only when the worker that opened its call left it: the row its opening kept
# must not stand in the way, or a call whose worker died would go to nobody.
async def test_a_room_a_worker_opened_is_kept_anew_when_it_is_offered_again(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    room, now = f"room_{uuid4().hex}", time.time()
    async with sessions.begin() as session:
        offers = OfferRepository(session)
        assert await offers.open(room, SANDBOX, Dispatch(agent="recepcion").dump(), now)
        assert await offers.claim(room, 0, agent_name(SANDBOX, "w1"), now)
        assert await offers.open(room, SANDBOX, Dispatch(agent="recepcion").dump(), now) is None
        await offers.mark_opened(room, now + 1)
        due = [offer.room for offer in await offers.list_due(now + 60, 1000)]
        assert room not in due, "a room a worker opened is offered to nobody else"
        again = await offers.open(room, SANDBOX, Dispatch(agent="recepcion").dump(), now + 2)
        assert again is not None and (again.worker, again.offers, again.opened_at) == (None, 0, None)
        await offers.forget(room)


def test_an_offer_takes_its_workers_slot_until_opened_and_then_until_the_next_beat() -> None:
    worker = a_worker("w1", active=0, seen_at=100.0)
    name = worker.agent_name or ""
    offered: list[tuple[str, float | None]] = [(name, None), (name, 99.0), (name, 101.0)]
    assert slots.count_in_flight(offered, [worker]) == {name: 2}
    assert slots.count_in_flight([(name, 99.0)], [worker]) == {}


# 2026-11-24: the gateway's heartbeat said a seat free before LiveKit heard its worker available, the
# room's job went to nobody, and twelve seconds later the room was sent to the overflow: its one
# worker had been tried. Ten of sixty simulated calls of a comparison heard "all our lines are busy".
async def test_a_room_its_only_worker_did_not_open_is_offered_to_it_again(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    servers, roster = per_world(), Roster()
    offering = Offering(sessions, servers=servers, roster=roster)
    only = f"w_{uuid4().hex}"
    roster.workers[(SANDBOX, only)] = a_worker(only, active=0, max_jobs=2, fleet=SANDBOX)
    room, late = f"room_{uuid4().hex}", time.time() - OFFERED_AGAIN_AFTER_S - 1
    try:
        async with sessions.begin() as session:
            offers = OfferRepository(session)
            assert await offers.open(room, SANDBOX, Dispatch(agent="recepcion").dump(), late)
            assert await offers.claim(room, 0, agent_name(SANDBOX, only), late)
        kept = await _kept(sessions, room)
        assert kept is not None
        assert await offering.offer_again(kept) == agent_name(SANDBOX, only)
    finally:
        await offering.forget(room)
        for server in servers.values():
            await server.aclose()


async def test_a_simulated_callers_room_waits_for_a_seat_where_a_callers_is_sent_the_overflow(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    servers, roster = per_world(), Roster()
    offering = Offering(sessions, servers=servers, roster=roster)
    full = f"w_{uuid4().hex}"
    roster.workers[(SANDBOX, full)] = a_worker(full, active=2, max_jobs=2, fleet=SANDBOX)
    simulated, real = f"room_{uuid4().hex}", f"room_{uuid4().hex}"
    try:
        assert await offering.offer(simulated, SANDBOX, Dispatch(agent="recepcion", persona="hurried")) is None
        assert await _kept(sessions, simulated) is not None, "it waits in the table for the next sweep"
        assert await offering.offer(real, SANDBOX, Dispatch(agent="recepcion")) == overflow_name(SANDBOX)
    finally:
        await offering.forget(simulated)
        await offering.forget(real)
        for server in servers.values():
            await server.aclose()


# A room that was rung and that nobody opened waits for the sweep to ring it again. A caller that only
# waits must not take the seat that frees first: on 2026-11-24 three callers that had lost theirs were
# passed by every caller behind them, and gave up.
async def test_a_caller_that_waits_lets_a_room_that_lost_its_seat_go_first(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    servers, roster = per_world(), Roster()
    offering = Offering(sessions, servers=servers, roster=roster)
    only = f"w_{uuid4().hex}"
    fleet = f"fleet-{uuid4().hex}"
    roster.workers[(fleet, only)] = a_worker(only, active=0, max_jobs=2, fleet=fleet)
    lost, behind = f"room_{uuid4().hex}", f"room_{uuid4().hex}"
    late = time.time() - OFFERED_AGAIN_AFTER_S - 1
    try:
        async with sessions.begin() as session:
            offers = OfferRepository(session)
            assert await offers.open(lost, fleet, Dispatch(agent="recepcion", persona="hurried").dump(), late)
            assert await offers.claim(lost, 0, agent_name(fleet, only), late)
            assert await offers.count_due(fleet, time.time() - OFFERED_AGAIN_AFTER_S) == 1
            await offers.mark_opened(lost, time.time())
            assert await offers.count_due(fleet, time.time() - OFFERED_AGAIN_AFTER_S) == 0, (
                "opened: it waits for nobody"
            )
    finally:
        await offering.forget(lost)
        await offering.forget(behind)
        for server in servers.values():
            await server.aclose()
