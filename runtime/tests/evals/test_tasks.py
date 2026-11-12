"""What a gateway plays: each run holds its agent under a lease, and each org's simulated calls are counted at once."""

import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.actor import Scope
from runtime.enums import Env
from runtime.evals import tasks
from runtime.evals.tasks import Runner, Simulations, TooManyAtOnce
from runtime.exceptions import Conflict
from runtime.signal import LocalSignal
from tests.conftest import needs_the_database, until

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
