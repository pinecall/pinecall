"""What evals plays: a run holds its agent by a lease, an org's simulated calls are counted, a process plays callers."""

import asyncio
import time
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.actor import Scope
from runtime.enums import Env
from runtime.evals import tasks
from runtime.evals.models import CallerJob
from runtime.evals.repository import CallerJobRepository
from runtime.evals.tasks import Callers, Runner, Simulations, TooManyAtOnce
from runtime.exceptions import Conflict
from runtime.signal import LocalSignal
from tests.conftest import Tenant, make_tenant, needs_the_database, until

ACME = Scope("org_acme", Env.sandbox)
OTHER = Scope("org_other", Env.sandbox)
# What an org may have on the line at once is its quotas' to say; these tests say ten.
AT_ONCE = 10


# A renewal that fails is said with its run and the next pass renews again: each run's renewal stands
# under `survive`, and the passes under `kit.Loops` (`tests/kit/test_loops.py`). Until 2026-11 each run
# renewed its own lease in a `while True` on a bare task: one that raised ended, the lease ran out
# under a run still playing, and another run took the agent it was driving.
def test_the_leases_are_renewed_by_a_loop_the_process_starts_well_inside_a_lease() -> None:
    assert tasks.renew_leases.name == "eval-run-leases"
    assert tasks.renew_leases.every_s < tasks.LEASED_S / 2


@needs_the_database
async def test_a_run_holds_its_agent_on_every_gateway_until_it_lets_go(
    sessions: async_sessionmaker[AsyncSession], agent: str
) -> None:
    """The lease is in the database: a run on one gateway holds the agent on another, which names it."""
    here, there = Runner(sessions), Runner(sessions)
    await here.hold("run_1", agent)
    with pytest.raises(Conflict, match="run_1"):
        await there.hold("run_2", agent)
    await here.renew()
    with pytest.raises(Conflict, match="run_1"):
        await there.hold("run_2", agent)
    await here.let_go("run_1", agent)
    await there.hold("run_2", agent)
    await there.let_go("run_2", agent)


# ── the calls on the line at once ──


async def waiting_on(ended: asyncio.Event) -> None:
    """A call that lasts until it is told to end."""
    await ended.wait()


async def test_a_call_counts_from_the_moment_it_is_admitted_until_it_ends() -> None:
    simulations = Simulations(LocalSignal())
    ended = asyncio.Event()
    simulations.take_place("call_1", ACME, AT_ONCE)
    assert simulations.count(ACME.org, ACME.env) == 1
    simulations.play("call_1", waiting_on(ended))
    assert simulations.count(ACME.org, ACME.env) == 1
    assert simulations.count(ACME.org, Env.production) == 0
    assert simulations.count(OTHER.org, OTHER.env) == 0
    ended.set()
    await until(lambda: simulations.count(ACME.org, ACME.env) == 0)
    await simulations.stop()


async def test_a_call_refused_after_it_was_admitted_gives_its_place_back() -> None:
    simulations = Simulations(LocalSignal())
    simulations.take_place("call_1", ACME, AT_ONCE)
    simulations.give_back("call_1")
    assert simulations.count(ACME.org, ACME.env) == 0
    async with simulations.hold_place("call_2", ACME, AT_ONCE):
        assert simulations.count(ACME.org, ACME.env) == 1
    assert simulations.count(ACME.org, ACME.env) == 0
    await simulations.stop()


async def test_a_call_past_the_orgs_most_at_once_in_an_env_is_refused_and_told_when_to_ask_again() -> None:
    simulations = Simulations(LocalSignal())
    ended = asyncio.Event()
    for n in range(AT_ONCE):
        simulations.take_place(f"call_{n}", ACME, AT_ONCE)
        simulations.play(f"call_{n}", waiting_on(ended))
    with pytest.raises(TooManyAtOnce, match="10 simulated calls on the line in sandbox") as refused:
        simulations.take_place("call_past", ACME, AT_ONCE)
    assert refused.value.status == 429 and refused.value.retry_after_s is not None
    # Another org, and the org's other env, are not held to this org's calls.
    simulations.take_place("another_orgs", OTHER, AT_ONCE)
    simulations.take_place("in_production", Scope(ACME.org, Env.production), AT_ONCE)
    ended.set()
    await until(lambda: simulations.count(ACME.org, ACME.env) == 0)
    simulations.take_place("once_one_ended", ACME, AT_ONCE)
    await simulations.stop()


# Four requests at once on one gateway, each awaiting its database between the count and the
# call's start (2026-10-21: four placed in one burst were all answered 200).
async def test_a_burst_on_one_gateway_never_passes_the_ceiling() -> None:
    simulations = Simulations(LocalSignal())
    ended = asyncio.Event()
    refused: list[str] = []

    async def placed(call: str) -> None:
        try:
            simulations.take_place(call, ACME, AT_ONCE)
        except TooManyAtOnce:
            refused.append(call)
            return
        await asyncio.sleep(0.01)
        simulations.play(call, waiting_on(ended))

    await asyncio.gather(*(placed(f"call_{n}") for n in range(AT_ONCE + 3)))
    assert len(refused) == 3
    assert simulations.count(ACME.org, ACME.env) == AT_ONCE
    ended.set()
    await until(lambda: simulations.count(ACME.org, ACME.env) == 0)
    await simulations.stop()


async def test_every_gateway_counts_the_calls_the_others_play() -> None:
    signal = LocalSignal()
    here, there = Simulations(signal), Simulations(signal)
    await here.start()
    await there.start()
    ended = asyncio.Event()
    try:
        # The listeners subscribe on their first turn; a count said before it is said again each beat.
        await asyncio.sleep(0)
        # All but one seat taken here; the last one there fills the line as both gateways count it.
        for n in range(AT_ONCE - 1):
            here.take_place(f"call_{n}", ACME, AT_ONCE)
            here.play(f"call_{n}", waiting_on(ended))
        await until(lambda: there.count(ACME.org, ACME.env) == AT_ONCE - 1)
        there.take_place("call_last", ACME, AT_ONCE)
        there.play("call_last", waiting_on(ended))
        await until(lambda: here.count(ACME.org, ACME.env) == AT_ONCE)
        with pytest.raises(TooManyAtOnce):
            there.take_place("call_past", ACME, AT_ONCE)
        ended.set()
        await until(lambda: here.count(ACME.org, ACME.env) == 0)
    finally:
        await here.stop()
        await there.stop()


# ── an org's own ceiling ──


async def test_an_org_given_more_places_at_once_takes_them_and_no_more() -> None:
    """The ceiling is the org's own when it has one: its quotas' calls at once, not the platform's ten."""
    simulations = Simulations(LocalSignal())
    for n in range(AT_ONCE + 2):
        simulations.take_place(f"call_{n}", ACME, AT_ONCE + 2)
    with pytest.raises(TooManyAtOnce):
        simulations.take_place("one_more", ACME, AT_ONCE + 2)
    with pytest.raises(TooManyAtOnce):
        simulations.take_place("anothers", OTHER, 0)
    assert simulations.count(ACME.org, ACME.env) == AT_ONCE + 2


# ── the callers a process plays ──


# Placed now, a moment apart in the order given: the suite's gateways settle what no process took for
# three quarters of an hour, on the one database every test is on.
def a_job(org: str, call: str, after_s: float) -> CallerJob:
    """A caller that waits for a process: its simulation said, nobody playing it."""
    placed_at = time.time() + after_s / 1000
    return CallerJob(call=call, org=org, env=Env.sandbox, agent="front-desk", document={}, placed_at=placed_at)


async def placed(sessions: async_sessionmaker[AsyncSession], *jobs: CallerJob) -> list[str]:
    async with sessions.begin() as session:
        for job in jobs:
            session.add(job)
    return [job.call for job in jobs]


async def job_of(sessions: async_sessionmaker[AsyncSession], call: str) -> CallerJob:
    async with sessions.begin() as session:
        found = await CallerJobRepository(session).find(call)
    assert found is not None
    return found


class Played:
    """What a process was handed to play: each caller stays on the line until the test lets it end."""

    def __init__(self) -> None:
        self.by: list[tuple[str, str]] = []
        self.cut: list[str] = []
        self.ended = asyncio.Event()

    async def __call__(self, job: CallerJob, process: str) -> None:
        self.by.append((process, job.call))
        try:
            await self.ended.wait()
        except asyncio.CancelledError:
            self.cut.append(job.call)
            raise


def a_process(sessions: async_sessionmaker[AsyncSession], play: Played, name: str, at_once: int = 3) -> Callers:
    return Callers(sessions, play, name=name, at_once=at_once)


# 2026-11-25: a simulated caller was a task of the gateway that took its request, nineteen at once on
# one loop. A caller is a row now: whichever process claims it plays it, and no other does.
@needs_the_database
@pytest.mark.usefixtures("the_callers_to_itself")
async def test_a_caller_is_played_by_the_one_process_that_claims_it_and_a_process_plays_no_more_than_its_most(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    calls = await placed(sessions, *(a_job(tenant.org, f"call_{uuid4().hex}", float(at)) for at in range(5)))
    play = Played()
    here, there = a_process(sessions, play, "here", at_once=2), a_process(sessions, play, "there", at_once=2)
    await asyncio.gather(here.claim(), there.claim(), here.claim(), there.claim())
    await until(lambda: len(play.by) >= 4)
    assert sorted(call for _, call in play.by) == sorted(calls[:4]), "each of the first four once, the fifth waits"
    assert (here.playing, there.playing) == (2, 2)
    assert (await job_of(sessions, calls[4])).claimed_by is None
    claimed = [str((await job_of(sessions, call)).claimed_by) for call in calls[:4]]
    assert sorted(claimed) == ["here", "here", "there", "there"]
    # A process with room again takes the one that waited; with nothing waiting, a pass takes nothing.
    play.ended.set()
    await until(lambda: here.playing == 0 and there.playing == 0)
    play.ended.clear()
    await here.claim()
    await until(lambda: play.by[-1] == ("here", calls[4]))
    assert here.playing == 1
    await there.claim()
    assert there.playing == 0
    play.ended.set()
    await here.stop(5.0)
    await there.stop(5.0)


# One org's comparison places ten callers; another org places one after them. A process that frees takes
# the caller of the org that holds none, as a fleet's seats are shared (`fleet.service.shares`).
@needs_the_database
@pytest.mark.usefixtures("the_callers_to_itself")
async def test_the_caller_of_the_org_that_holds_the_fewest_is_claimed_first(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    another = await make_tenant(sessions)
    theirs = await placed(sessions, *(a_job(tenant.org, f"call_{uuid4().hex}", float(at)) for at in range(4)))
    ours = await placed(sessions, a_job(another.org, f"call_{uuid4().hex}", 10.0))
    play = Played()
    process = a_process(sessions, play, "one", at_once=3)
    await process.claim()
    await until(lambda: len(play.by) == 3)
    assert [call for _, call in play.by] == [theirs[0], ours[0], theirs[1]]
    play.ended.set()
    await process.stop(5.0)


class AClock:
    """A clock a test moves."""

    def __init__(self) -> None:
        self.now = time.time()

    def __call__(self) -> float:
        return self.now


# The gaps the room heard on 2026-11-25 were a loop behind its clock. A process reads the clock twenty
# times a second: a reading that came late means the callers it plays already cost it its time.
@needs_the_database
@pytest.mark.usefixtures("the_callers_to_itself")
async def test_a_process_whose_loop_woke_late_claims_no_caller_until_it_has_rested(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    (call,) = await placed(sessions, a_job(tenant.org, f"call_{uuid4().hex}", 1.0))
    play, ticks = Played(), AClock()
    process = Callers(sessions, play, name="late", at_once=3, ticks=ticks)
    process.read_clock()
    ticks.now += tasks.THE_CLOCK_IS_READ_EVERY_S
    process.read_clock()
    assert process.takes_more, "a reading on time rests nobody"
    ticks.now += tasks.THE_CLOCK_IS_READ_EVERY_S + 2 * tasks.A_LATE_READING_S
    process.read_clock()
    assert not process.takes_more
    await process.claim()
    assert play.by == [] and (await job_of(sessions, call)).claimed_by is None
    ticks.now += tasks.A_LATE_PROCESS_RESTS_S
    await process.claim()
    await until(lambda: play.by == [("late", call)])
    play.ended.set()
    await until(lambda: process.playing == 0)


# A release of the gateway ended every simulated call on the line with it. A process told to stop takes
# no other caller and ends when the ones it plays do; what outlives the time it is given is cut, and its
# task is left to say how (`service.caller_jobs.play_claimed`).
@needs_the_database
@pytest.mark.usefixtures("the_callers_to_itself")
async def test_a_process_told_to_stop_claims_no_other_caller_and_ends_with_the_ones_it_plays(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    first, second = await placed(
        sessions, a_job(tenant.org, f"call_{uuid4().hex}", 1.0), a_job(tenant.org, f"call_{uuid4().hex}", 2.0)
    )
    play = Played()
    process = a_process(sessions, play, "stopping", at_once=1)
    await process.claim()
    await until(lambda: play.by == [("stopping", first)])
    stopping = asyncio.ensure_future(process.stop(30.0))
    await asyncio.sleep(0.05)
    assert not stopping.done(), "it waits for the caller it plays"
    await process.claim()
    assert play.by == [("stopping", first)] and (await job_of(sessions, second)).claimed_by is None
    play.ended.set()
    await stopping
    assert play.cut == [] and process.playing == 0
    # Another process plays the one it left waiting.
    other = a_process(sessions, Played(), "another")
    await other.claim()
    assert (await job_of(sessions, second)).claimed_by == "another"
    await other.stop(0.0)


@needs_the_database
@pytest.mark.usefixtures("the_callers_to_itself")
async def test_a_caller_that_outlives_the_time_a_stopping_process_is_given_is_cut(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    (call,) = await placed(sessions, a_job(tenant.org, f"call_{uuid4().hex}", 1.0))
    play = Played()
    process = a_process(sessions, play, "cut")
    await process.claim()
    await until(lambda: len(play.by) == 1)
    await process.stop(0.0)
    assert play.cut == [call] and process.playing == 0


# A process says it still plays what it claimed; what it says nothing of for forty seconds is taken up.
@needs_the_database
@pytest.mark.usefixtures("the_callers_to_itself")
async def test_a_process_says_it_still_plays_each_caller_it_claimed(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    (call,) = await placed(sessions, a_job(tenant.org, f"call_{uuid4().hex}", 1.0))
    play, clock = Played(), AClock()
    process = Callers(sessions, play, name="saying", at_once=1, clock=clock)
    began = clock.now
    await process.claim()
    claimed = await job_of(sessions, call)
    assert (claimed.claimed_by, claimed.heard_at, claimed.played) == ("saying", began, 1)
    clock.now += tasks.A_CALLER_IS_SAID_EVERY_S
    await process.renew()
    assert (await job_of(sessions, call)).heard_at == began + tasks.A_CALLER_IS_SAID_EVERY_S
    assert tasks.say_callers.every_s * 2 < tasks.LEFT_AFTER_S, "two sayings may be missed before a caller is taken up"
    play.ended.set()
    await process.stop(5.0)
