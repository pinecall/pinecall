"""The offers: a room of no env's fleet is let go, a room a worker took is not rung again, a seat is taken in turn."""

import time
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from livekit import api
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from runtime.enums import Env
from runtime.fleet.models import Offer, Turn
from runtime.fleet.repository import OfferRepository, TurnRepository
from runtime.fleet.schemas import WorkerStatus
from runtime.fleet.service import slots
from runtime.fleet.service.dispatches import agent_name, overflow_name
from runtime.fleet.service.envs import PRODUCTION, SANDBOX
from runtime.fleet.service.offers import (
    A_SEAT_IS_HELD_AT_MOST_S,
    A_WAITER_ASKS_WITHIN_S,
    FORGOTTEN_AFTER_S,
    OFFERED_AGAIN_AFTER_S,
    Offering,
    list_next,
)
from runtime.fleet.service.roster import Roster
from runtime.wire.dispatch import Dispatch
from tests.conftest import needs_the_database
from tests.fakes.livekit import per_world

pytestmark = needs_the_database

THE_SUITES_FLEETS = text("select pg_advisory_lock(hashtext('tests:the fleets seats'))")
GIVEN_BACK = text("select pg_advisory_unlock(hashtext('tests:the fleets seats'))")


# A fleet's seats, its rooms due again and its line are one per database, and every worker of the
# suite runs on the one database: a caller another test left waiting for a moment would be seated
# before this test's own. The tests of this file take the fleets one at a time.
@pytest.fixture(autouse=True)
async def the_fleets_to_itself(engine: AsyncEngine) -> AsyncIterator[None]:
    async with engine.connect() as held:
        await held.execute(THE_SUITES_FLEETS)
        try:
            yield
        finally:
            await held.execute(GIVEN_BACK)


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
        await offering.forget(second)
        for server in servers.values():
            await server.aclose()


# 2026-11-24: simulations held every seat of production's sandbox, and the people who called in that
# quarter of an hour were sent the overflow's sentence. A caller that can wait leaves a quarter of the
# fleet's seats free; a person's room is offered the worker all the same.
async def test_a_caller_that_can_wait_leaves_a_quarter_of_the_fleets_seats_to_people(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    servers, roster = per_world(), Roster()
    offering = Offering(sessions, servers=servers, roster=roster)
    only = f"w_{uuid4().hex}"
    roster.workers[(SANDBOX, only)] = a_worker(only, active=0, max_jobs=8, fleet=SANDBOX)
    seated = [f"room_{uuid4().hex}" for _ in range(6)]
    one_more, a_person = f"room_{uuid4().hex}", f"room_{uuid4().hex}"
    try:
        for room in seated:
            assert await offering.take_seat(room, SANDBOX, Dispatch(agent="recepcion")) is not None
        assert await offering.take_seat(one_more, SANDBOX, Dispatch(agent="recepcion")) is None, "six of eight"
        assert await offering.has_a_slot(SANDBOX), "two seats are free, and they are a person's"
        assert await offering.offer(a_person, SANDBOX, Dispatch(agent="recepcion")) == agent_name(SANDBOX, only)
    finally:
        for room in (*seated, one_more, a_person):
            await offering.forget(room)
        for server in servers.values():
            await server.aclose()


def test_a_small_fleet_and_one_that_counts_no_seats_keep_none_for_people() -> None:
    now = time.time()
    assert (
        slots.count_kept_for_people([a_worker("a", active=0, max_jobs=8), a_worker("b", active=0, max_jobs=4)], now)
        == 3
    )
    assert slots.count_kept_for_people([a_worker("a", active=0, max_jobs=3)], now) == 0
    counts_none = a_worker("a", active=0).model_copy(update={"max_jobs": None})
    assert slots.count_kept_for_people([counts_none], now) == 0


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


# 2026-11-25: nineteen simulated calls started on one worker at once, and a job's process took over
# twelve seconds from its dispatch to joining its room. The sweep read each room as one LiveKit gave to
# nobody and rang it again, and the second job ended the call the first was holding. A worker says the
# room is its own as it accepts the job; a room nobody took is still LiveKit's loss, and is rung again.
async def test_a_room_its_worker_took_is_not_rung_again_however_long_its_job_takes_to_start(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    servers, roster = per_world(), Roster()
    offering = Offering(sessions, servers=servers, roster=roster)
    only = f"w_{uuid4().hex}"
    roster.workers[(SANDBOX, only)] = a_worker(only, active=0, max_jobs=8, fleet=SANDBOX)
    taken, given_to_nobody = f"room_{uuid4().hex}", f"room_{uuid4().hex}"
    rung = time.time() - OFFERED_AGAIN_AFTER_S - 5
    async with sessions.begin() as session:
        offers = OfferRepository(session)
        for room in (taken, given_to_nobody):
            assert await offers.open(room, SANDBOX, Dispatch(agent="recepcion").dump(), rung)
            assert await offers.claim(room, 0, agent_name(SANDBOX, only), rung)
    try:
        await offering.say_opened(taken)
        offered = await offering.sweep()
        assert given_to_nobody in offered, "a job LiveKit gave to nobody is rung again"
        assert taken not in offered, "a room a worker accepted the job of is that worker's"
        kept = await _kept(sessions, taken)
        assert kept is not None and kept.offers == 1
    finally:
        await offering.forget(taken)
        await offering.forget(given_to_nobody)
        for server in servers.values():
            await server.aclose()


# A job accepted and never started (LiveKit assigned it to nobody after all, or no process could be
# launched for it) is given back by the worker that took it, and by no other.
async def test_a_room_its_worker_could_not_start_the_job_of_is_rung_again(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    servers, roster = per_world(), Roster()
    offering = Offering(sessions, servers=servers, roster=roster)
    only = f"w_{uuid4().hex}"
    roster.workers[(SANDBOX, only)] = a_worker(only, active=0, max_jobs=8, fleet=SANDBOX)
    room, rung = f"room_{uuid4().hex}", time.time() - OFFERED_AGAIN_AFTER_S - 5
    async with sessions.begin() as session:
        offers = OfferRepository(session)
        assert await offers.open(room, SANDBOX, Dispatch(agent="recepcion").dump(), rung)
        assert await offers.claim(room, 0, agent_name(SANDBOX, only), rung)
    try:
        await offering.say_opened(room)
        await offering.say_dropped(room, agent_name(SANDBOX, "another"))
        assert room not in await offering.sweep(), "only the worker the room was offered to gives it back"
        await offering.say_dropped(room, agent_name(SANDBOX, only))
        assert room in await offering.sweep()
    finally:
        await offering.forget(room)
        for server in servers.values():
            await server.aclose()


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


# ── the line for a seat, shared between the orgs in it ──


def a_fleet_of(roster: Roster, seats: int, *, taken: int = 0) -> str:
    """One worker of the sandbox's fleet with so many seats, some of them holding calls; its name."""
    only = f"w_{uuid4().hex}"
    roster.workers[(SANDBOX, only)] = a_worker(only, active=taken, max_jobs=seats, fleet=SANDBOX)
    return only


def of(org: str) -> Dispatch:
    """A waiting caller's dispatch, placed by the org."""
    return Dispatch(agent="recepcion", org=org, persona="in-a-hurry")


async def _turn(sessions: async_sessionmaker[AsyncSession], room: str) -> Turn | None:
    async with sessions.begin() as session:
        return await session.get(Turn, room)


# 2026-11-25: a comparison of two hundred calls held the sandbox's seats for over an hour, and a seat
# that freed went to whichever caller asked first, which was the comparison's own next one. Two
# gateways are two dispatchers on the one table: the answer is the rows', whoever asks.
async def test_a_seat_that_frees_goes_to_the_org_that_holds_the_fewest_on_whichever_gateway_it_asks(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    servers, roster = per_world(), Roster()
    one_gateway = Offering(sessions, servers=servers, roster=roster)
    another = Offering(sessions, servers=servers, roster=roster)
    only = a_fleet_of(roster, seats=3)
    acme, bolt = f"acme_{uuid4().hex}", f"bolt_{uuid4().hex}"
    held = [f"room_{uuid4().hex}" for _ in range(3)]
    next_of_acme, first_of_bolt, second_of_bolt = (f"room_{uuid4().hex}" for _ in range(3))
    try:
        for room in held:
            assert await one_gateway.take_seat(room, SANDBOX, of(acme)) is not None, "alone, an org takes every seat"
        assert await one_gateway.take_seat(next_of_acme, SANDBOX, of(acme)) is None
        assert await another.take_seat(first_of_bolt, SANDBOX, of(bolt)) is None
        assert await another.take_seat(second_of_bolt, SANDBOX, of(bolt)) is None
        # One of acme's calls ends, and its seat is given back.
        await one_gateway.forget(held[0])
        assert await one_gateway.take_seat(next_of_acme, SANDBOX, of(acme)) is None, "acme holds two and bolt none"
        assert await one_gateway.take_seat(second_of_bolt, SANDBOX, of(bolt)) is None, "bolt's first caller is first"
        seat = await another.take_seat(first_of_bolt, SANDBOX, of(bolt))
        assert seat is not None and seat.worker == agent_name(SANDBOX, only)
        turn = await _turn(sessions, first_of_bolt)
        assert turn is not None and turn.seated_at is not None and turn.org == bolt
        # Nobody's call was ended to make room: acme's two are still seated.
        assert [await _turn(sessions, room) is not None for room in held] == [False, True, True]
    finally:
        for room in (*held, next_of_acme, first_of_bolt, second_of_bolt):
            await one_gateway.forget(room)
        for server in servers.values():
            await server.aclose()


async def test_several_seats_free_at_once_are_taken_by_the_first_of_the_line_in_any_order(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    servers, roster = per_world(), Roster()
    offering = Offering(sessions, servers=servers, roster=roster)
    only = a_fleet_of(roster, seats=3, taken=3)
    acme, bolt = f"acme_{uuid4().hex}", f"bolt_{uuid4().hex}"
    rooms = {name: f"room_{uuid4().hex}" for name in ("acme-1", "acme-2", "acme-3", "bolt-1")}
    try:
        for name, room in rooms.items():
            assert await offering.take_seat(room, SANDBOX, of(acme if name.startswith("acme") else bolt)) is None
        # Two of the worker's calls end together: one seat is acme's first caller's, the other bolt's.
        roster.workers[(SANDBOX, only)] = a_worker(only, active=1, max_jobs=3, fleet=SANDBOX)
        assert await offering.take_seat(rooms["acme-2"], SANDBOX, of(acme)) is None
        assert await offering.take_seat(rooms["bolt-1"], SANDBOX, of(bolt)) is not None
        assert await offering.take_seat(rooms["acme-3"], SANDBOX, of(acme)) is None
        assert await offering.take_seat(rooms["acme-1"], SANDBOX, of(acme)) is not None
        assert await offering.take_seat(rooms["acme-2"], SANDBOX, of(acme)) is None, "both seats are taken"
    finally:
        for room in rooms.values():
            await offering.forget(room)
        for server in servers.values():
            await server.aclose()


# A caller whose wait ended (its simulation stopped, its gateway gone) asks no more. The one behind it
# is not held back by it: at once when it says so, and within seconds when it only went silent.
async def test_a_caller_that_left_the_line_holds_nobody_back(sessions: async_sessionmaker[AsyncSession]) -> None:
    fleet, now = f"fleet_{uuid4().hex}", time.time()
    gave_up, went_silent, waits = (f"room_{uuid4().hex}" for _ in range(3))
    async with sessions.begin() as session:
        turns = TurnRepository(session)
        await turns.ask(gave_up, fleet, "acme", now - 30)
        await turns.ask(went_silent, fleet, "acme", now - 20)
        await turns.ask(went_silent, fleet, "acme", now - A_WAITER_ASKS_WITHIN_S - 1)
        await turns.ask(waits, fleet, "acme", now - 10)
        for room in (gave_up, waits):
            await turns.ask(room, fleet, "acme", now)
        assert await list_next(turns, fleet, 1, now) == [gave_up]
        await turns.forget(gave_up)
        assert await list_next(turns, fleet, 1, now) == [waits], "the silent one is passed over"
        # It asks again: it was only slow, and its place is the one its first ask gave it.
        await turns.ask(went_silent, fleet, "acme", now)
        assert await list_next(turns, fleet, 2, now) == [went_silent, waits]
        await turns.forget_gone(now + 1, now - A_SEAT_IS_HELD_AT_MOST_S)
        assert await list_next(turns, fleet, 2, now) == []


# A seat nobody gave back (its gateway gone, its room's end unheard) is its org's for as long as a
# call that waited for one may last, and no longer: the org is not kept behind the others by it for good.
async def test_a_seat_nobody_gave_back_stops_counting_as_its_orgs(sessions: async_sessionmaker[AsyncSession]) -> None:
    fleet, now = f"fleet_{uuid4().hex}", time.time()
    lost, of_acme, of_bolt = (f"room_{uuid4().hex}" for _ in range(3))
    async with sessions.begin() as session:
        turns = TurnRepository(session)
        await turns.ask(lost, fleet, "acme", now - 60)
        await turns.seat(lost, now - 60)
        await turns.ask(of_acme, fleet, "acme", now - 5)
        await turns.ask(of_bolt, fleet, "bolt", now)
        assert await turns.count_held(fleet, now - A_SEAT_IS_HELD_AT_MOST_S) == {"acme": 1}
        assert await list_next(turns, fleet, 1, now) == [of_bolt], "acme holds one and bolt none"
        later = now + A_SEAT_IS_HELD_AT_MOST_S
        for room in (of_acme, of_bolt):
            await turns.ask(room, fleet, "acme" if room == of_acme else "bolt", later)
        assert await list_next(turns, fleet, 1, later) == [of_acme], "the seat is past any call: acme asked first"
        await turns.forget_gone(later - FORGOTTEN_AFTER_S, later - A_SEAT_IS_HELD_AT_MOST_S)
        assert await session.get(Turn, lost) is None
        for room in (of_acme, of_bolt):
            await turns.forget(room)


async def test_a_pass_of_the_sweep_lets_go_the_callers_that_stopped_asking_and_keeps_the_ones_seated(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    fleet, now = f"fleet_{uuid4().hex}", time.time()
    stopped, seated = f"room_{uuid4().hex}", f"room_{uuid4().hex}"
    async with sessions.begin() as session:
        turns = TurnRepository(session)
        await turns.ask(stopped, fleet, "acme", now - FORGOTTEN_AFTER_S - 5)
        await turns.ask(seated, fleet, "acme", now - FORGOTTEN_AFTER_S - 5)
        await turns.seat(seated, now - FORGOTTEN_AFTER_S - 5)
    offering = Offering(sessions, servers={}, roster=Roster())
    await offering.sweep()
    assert await _turn(sessions, stopped) is None
    assert await _turn(sessions, seated) is not None, "a call lasts longer than a wait is forgotten in"
    await offering.forget(seated)
    assert await _turn(sessions, seated) is None
