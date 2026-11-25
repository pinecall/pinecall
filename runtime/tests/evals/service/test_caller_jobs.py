"""A caller's job: kept whole on its row, its place on the org's line, and how the process that claimed it leaves it."""

import asyncio
import time
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.actor import Scope
from runtime.calls.log.store import Store
from runtime.enums import Env
from runtime.evals.models import CallerJob
from runtime.evals.parts import CallerParts, Harness
from runtime.evals.repository import CallerJobRepository
from runtime.evals.service import caller_jobs
from runtime.evals.service.simulated_calls import Simulation
from runtime.evals.tasks import TooManyAtOnce
from runtime.exceptions import ServiceUnavailable
from runtime.judging import service as judging
from runtime.kit.link import LinkShape
from tests.conftest import Gateway, Tenant, needs_the_database, needs_the_services

A_CALLER = judging.Persona(
    name="in-a-hurry",
    goal="I want the first cleaning you have.",
    style="short sentences",
    facts={"their name": "Tom Baker"},
    state={"visits": [{"id": "v-1"}]},
    voice="a-voice",
    expects=("The agent should book a time it read from the agenda.",),
    tags=("eval",),
    behavior=judging.Behavior(interrupts=0.5, speed=1.1, interferer_db=12.0, ambience="cafe"),
)


def a_simulation(org: str, call: str) -> Simulation:
    return Simulation(
        call=call,
        agent="front-desk",
        scope=Scope(org, Env.sandbox, "a-colleague"),
        persona=A_CALLER,
        turns=12,
        spoken=True,
        acts=judging.Behavior(interrupts=0.5, packet_loss=0.03, pause_s=1.5),
        state={"visits": [{"id": "v-1"}]},
        waits_for_slot=True,
        against={"llm": "acme/acme-1"},
        comparison="cmp_one",
        network=LinkShape(0.03, 40.0, 5.0, 64.0),
        rings="+14155550134",
        held_by=Scope(org, Env.sandbox, ""),
    )


# The process that plays a caller reads its row and nothing else of the request that placed it: what
# the caller is, how it acts, what the agent runs on for it, whose app holds the agent.
def test_a_simulation_is_played_as_it_was_placed_whichever_process_reads_its_row() -> None:
    placed = a_simulation("org_acme", "call_one")
    row = CallerJob(
        call="call_one",
        org="org_acme",
        env=Env.sandbox,
        agent="front-desk",
        comparison="cmp_one",
        document=caller_jobs.dump(placed, "in-a-hurry"),
        placed_at=1.0,
    )
    assert caller_jobs.load(row) == placed
    assert caller_jobs.pair_of(row) == ("in-a-hurry", {"llm": "acme/acme-1"})


# ── how the process that claimed a caller leaves it ──


async def claimed(sessions: async_sessionmaker[AsyncSession], org: str, process: str) -> CallerJob:
    call = f"call_{uuid4().hex}"
    document = caller_jobs.dump(a_simulation(org, call), "in-a-hurry")
    job = CallerJob(call=call, org=org, env=Env.sandbox, agent="front-desk", document=document, placed_at=time.time())
    async with sessions.begin() as session:
        session.add(job)
    async with sessions.begin() as session:
        taken = await CallerJobRepository(session).claim(process, time.time())
    assert taken is not None and taken.call == call
    return taken


async def row_of(sessions: async_sessionmaker[AsyncSession], call: str) -> CallerJob:
    async with sessions.begin() as session:
        found = await CallerJobRepository(session).find(call)
    assert found is not None
    return found


def parts_of(sessions: async_sessionmaker[AsyncSession], store: Store) -> CallerParts:
    """What a process plays a caller with, as far as leaving one goes: the database and the call's log."""
    return cast(CallerParts, SimpleNamespace(sessions=sessions, store=store))


def played_as(monkeypatch: pytest.MonkeyPatch, play: object, *, begun: bool = False) -> None:
    async def has_begun(_parts: CallerParts, _call: str) -> bool:
        return begun

    monkeypatch.setattr(caller_jobs, "play_spoken", play)
    monkeypatch.setattr(caller_jobs, "_has_begun", has_begun)


@needs_the_database
@pytest.mark.usefixtures("the_callers_to_itself")
async def test_a_caller_played_to_its_end_is_over_and_stands_for_its_call(
    sessions: async_sessionmaker[AsyncSession], store: Store, tenant: Tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    played: list[Simulation] = []

    async def play(_parts: CallerParts, simulation: Simulation) -> None:
        played.append(simulation)

    played_as(monkeypatch, play)
    job = await claimed(sessions, tenant.org, "me")
    await caller_jobs.play_claimed(parts_of(sessions, store), job, "me")
    row = await row_of(sessions, job.call)
    assert [one.call for one in played] == [job.call]
    assert row.ended_at is not None and not row.lost and row.broke is None


# 2026-11-25: a caller that broke before its call began was a warning in a gateway's log and a call left
# open. A process that plays callers cannot end a call (it has no live side): it says why on the row,
# and a gateway ends the call with it.
@needs_the_database
@pytest.mark.usefixtures("the_callers_to_itself")
async def test_a_caller_that_breaks_before_its_call_began_says_why_on_its_row(
    sessions: async_sessionmaker[AsyncSession], store: Store, tenant: Tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def refused(_parts: CallerParts, _simulation: Simulation) -> None:
        raise ServiceUnavailable("the simulated call could not be held: no agent joined room in 110s")

    async def broke(_parts: CallerParts, _simulation: Simulation) -> None:
        raise RuntimeError("select secret from vault")

    for play, why in (
        (refused, "the simulated call could not be held: no agent joined room in 110s"),
        (broke, "the gateway could not play this call's caller (RuntimeError): its log says why"),
    ):
        played_as(monkeypatch, play)
        job = await claimed(sessions, tenant.org, "me")
        with pytest.raises((ServiceUnavailable, RuntimeError)):
            await caller_jobs.play_claimed(parts_of(sessions, store), job, "me")
        assert (await row_of(sessions, job.call)).broke == why


# A release cuts what outlived the drain. A caller cut before its call began (it waited for a seat) is
# let go for another process to play whole; one cut on the line leaves a call that is over, said lost,
# which its comparison places again.
@needs_the_database
@pytest.mark.usefixtures("the_callers_to_itself")
async def test_a_caller_cut_before_its_call_began_is_another_processes_and_one_cut_on_the_line_is_lost(
    sessions: async_sessionmaker[AsyncSession], store: Store, tenant: Tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    on_the_line = asyncio.Event()

    async def play(_parts: CallerParts, _simulation: Simulation) -> None:
        on_the_line.set()
        await asyncio.Event().wait()

    for begun in (False, True):
        on_the_line.clear()
        played_as(monkeypatch, play)
        job = await claimed(sessions, tenant.org, "stopping")
        playing = asyncio.ensure_future(caller_jobs.play_claimed(parts_of(sessions, store), job, "stopping"))
        await on_the_line.wait()
        played_as(monkeypatch, play, begun=begun)
        playing.cancel()
        with pytest.raises(asyncio.CancelledError):
            await playing
        row = await row_of(sessions, job.call)
        if begun:
            assert row.ended_at is not None and row.lost
        else:
            assert (row.claimed_by, row.ended_at, row.lost, row.played) == (None, None, False, 1)
            # Claimed again, by another: played whole, once more.
            async with sessions.begin() as session:
                again = await CallerJobRepository(session).claim("another", time.time())
            assert again is not None and (again.call, again.claimed_by, again.played) == (job.call, "another", 2)
            async with sessions.begin() as session:
                await CallerJobRepository(session).end(job.call, "another", time.time(), lost=False)


# A caller let go before its call began may have rung its room first: a worker that took the room began
# a call nobody is on. The process that claims it again finds the call begun and plays nothing.
@needs_the_database
@pytest.mark.usefixtures("the_callers_to_itself")
async def test_a_caller_claimed_for_a_call_that_began_without_it_is_not_played(
    sessions: async_sessionmaker[AsyncSession], store: Store, tenant: Tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def play(_parts: CallerParts, _simulation: Simulation) -> None:
        raise AssertionError("a call that began is not played from its start")

    played_as(monkeypatch, play, begun=True)
    job = await claimed(sessions, tenant.org, "me")
    await caller_jobs.play_claimed(parts_of(sessions, store), job, "me")
    row = await row_of(sessions, job.call)
    assert row.ended_at is not None and row.lost


# A process that was taken for gone (it said nothing for forty seconds) and comes back writes nothing
# over the row another one took since.
@needs_the_database
@pytest.mark.usefixtures("the_callers_to_itself")
async def test_a_process_lets_go_of_no_caller_another_took_since(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    job = await claimed(sessions, tenant.org, "taken for gone")
    async with sessions.begin() as session:
        jobs = CallerJobRepository(session)
        await jobs.release(job.call, "taken for gone")
        again = await jobs.claim("another", time.time())
        assert again is not None
        await jobs.end(job.call, "taken for gone", time.time(), lost=True)
        await jobs.say_broke(job.call, "taken for gone", "it broke")
    row = await row_of(sessions, job.call)
    assert (row.claimed_by, row.ended_at, row.broke, row.lost) == ("another", None, None, False)


# ── its place on the org's line ──


# The place was a count in one gateway's memory, given back when its task ended. It is the job's row
# now, counted under the org's lock: the most at once holds whichever gateway is asked, and with the
# written calls a gateway still counts itself.
@needs_the_services
@pytest.mark.usefixtures("the_callers_to_itself")
async def test_a_spoken_calls_place_is_its_row_and_the_orgs_most_at_once_counts_rows_and_this_gateways_own(
    gateway: Gateway, sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    parts: Harness = gateway.state["harness"]
    scope = Scope(tenant.org, Env.sandbox)
    first, second, third = (f"call_{uuid4().hex}" for _ in range(3))
    await caller_jobs.take_place(parts, first, scope, "front-desk", None, 3)
    parts.simulations.take_place(second, scope, 3, beside=1)
    try:
        await caller_jobs.take_place(parts, third, scope, "front-desk", "cmp_one", 3)
        with pytest.raises(TooManyAtOnce, match="3 simulated calls on the line"):
            await caller_jobs.take_place(parts, f"call_{uuid4().hex}", scope, "front-desk", None, 3)
        with pytest.raises(TooManyAtOnce):
            parts.simulations.take_place(f"call_{uuid4().hex}", scope, 3, beside=2)
        async with sessions.begin() as session:
            assert await caller_jobs.count_placed(session, scope) == 2
        # A place whose simulation was never said is nothing a process claims.
        async with sessions.begin() as session:
            assert await CallerJobRepository(session).claim("a process", time.time()) is None
        await caller_jobs.give_place_back(parts, third)
        await caller_jobs.take_place(parts, third, scope, "front-desk", None, 3)
    finally:
        parts.simulations.give_back(second)
        await caller_jobs.give_place_back(parts, first)
        await caller_jobs.give_place_back(parts, third)
