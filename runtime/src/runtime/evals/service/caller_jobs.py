"""A caller's job: a spoken simulation as its row keeps it, its place on the line, played by whoever claimed it."""

import logging
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.actor import Scope
from runtime.enums import Env
from runtime.evals.models import CallerJob
from runtime.evals.parts import CallerParts, Harness
from runtime.evals.repository import CallerJobRepository
from runtime.evals.service.simulated_calls import Simulation, play_spoken, say_why
from runtime.evals.tasks import LEFT_AFTER_S, TooManyAtOnce
from runtime.judging import service as judging
from runtime.kit.link import LinkShape
from runtime.kit.loops import is_cancellation, survive
from runtime.kit.text import JsonObject
from runtime.livekit import close_room
from runtime.postgres import when_free
from runtime.scoping import box_wide

logger = logging.getLogger(__name__)

# A caller its process stopped playing is over: said on the row, which a comparison reads to place the
# call again, and on the log of a call that never began.
LEFT_BEFORE_IT_BEGAN = (
    "the process that played this call's caller stopped before the call began, twice: is the callers service up?"
)
# A caller is played whole by the process that claims it. One let go before its call began is claimed
# again, once: a caller that takes its process down with it would do so to every one.
PLAYED_AT_MOST = 2
# A caller placed waits for a process as long as it would wait for a seat of the fleet
# (`slots.WAITED_S`): past that nothing here plays callers, and its call says so.
NOBODY_PLAYS_AFTER_S = 45 * 60.0
NOBODY_PLAYED_IT = (
    "no process took this call's caller in {minutes:.0f} minutes: the callers service is not running, or every "
    "process of it was busy the whole time"
)
# A job that is over is kept an hour: a comparison reads what was lost of it while it is played. A place
# taken by a placing that never said its simulation (its gateway stopped in the middle) is given back
# after five minutes, which no placing takes.
KEPT_AFTER_ITS_END_S = 60 * 60.0
A_PLACING_TAKES_AT_MOST_S = 5 * 60.0
# One pass of a gateway settles this many of each kind: the rest wait for the next, two seconds on.
SETTLED_A_PASS = 20


# ── the simulation, as the row keeps it ──


# Kept whole, as it was placed: the caller briefed, how it acts, what the agent runs on for it. The
# process that plays it reads nothing of the agent's personas again, so a persona edited between the
# placing and the playing is played as it was asked for. `named` is the caller as the request named
# it, which a comparison counts its calls by.
def dump(simulation: Simulation, named: str) -> JsonObject:
    """The simulation as its job's row keeps it."""
    held = simulation.held_by
    return {
        "named": named,
        "holder": simulation.scope.holder,
        "persona": asdict(simulation.persona),
        "turns": simulation.turns,
        "acts": asdict(simulation.acts),
        "state": dict(simulation.state),
        "waits_for_slot": simulation.waits_for_slot,
        "against": dict(simulation.against),
        "network": asdict(simulation.network),
        "rings": simulation.rings,
        "held_by": None if held is None else {"org": held.org, "env": held.env.value, "holder": held.holder},
    }


def load(job: CallerJob) -> Simulation:
    """The simulation a job's row keeps, to play."""
    kept: Mapping[str, Any] = job.document or {}
    held: Mapping[str, Any] | None = kept.get("held_by")
    return Simulation(
        call=job.call,
        agent=job.agent,
        scope=Scope(job.org, job.env, str(kept.get("holder") or "")),
        persona=_persona_of(kept["persona"]),
        turns=int(kept["turns"]),
        spoken=True,
        acts=judging.Behavior(**kept["acts"]),
        state=dict(kept.get("state") or {}),
        waits_for_slot=bool(kept.get("waits_for_slot")),
        against=dict(kept.get("against") or {}),
        comparison=job.comparison,
        network=LinkShape(**kept["network"]),
        rings=kept.get("rings"),
        held_by=None if held is None else Scope(str(held["org"]), Env(held["env"]), str(held["holder"])),
    )


def _persona_of(kept: Mapping[str, Any]) -> judging.Persona:
    return judging.Persona(
        name=str(kept["name"]),
        goal=str(kept["goal"]),
        style=str(kept["style"]),
        about=str(kept.get("about") or ""),
        facts=dict(kept.get("facts") or {}),
        state=dict(kept.get("state") or {}),
        llm=kept.get("llm"),
        tts=kept.get("tts"),
        voice=kept.get("voice"),
        expects=tuple(kept.get("expects") or ()),
        tags=tuple(kept.get("tags") or ()),
        behavior=judging.Behavior(**kept["behavior"]),
    )


def pair_of(job: CallerJob) -> tuple[str, JsonObject]:
    """The caller as its request named it and what the agent ran on for it: what a comparison counts a call by."""
    kept: Mapping[str, Any] = job.document or {}
    return str(kept.get("named") or ""), dict(kept.get("against") or {})


# ── its place on the org's line ──


# A spoken call's place on its org's line is its job's row, from before anything that costs until the
# job is over, on every gateway alike: the count and the row are one step under the org's lock. Until
# 2026-11-25 the place was a count in the memory of the gateway that played the caller, said to the
# others on the signal: it was given back when that gateway's task ended, which no longer says anything
# of a caller another process plays. What a gateway still plays itself (a written call, a golden said
# out loud) is counted as it was, and counts here too.
async def take_place(parts: Harness, call: str, scope: Scope, agent: str, comparison: str | None, at_most: int) -> None:
    """Give the spoken call its place on its org's line; refused when the org has its most there already."""
    async with parts.sessions.begin() as session_:
        jobs = CallerJobRepository(session_)
        await jobs.take_turns(scope.org, scope.env)
        playing = await jobs.count_open(scope.org, scope.env) + parts.simulations.count(scope.org, scope.env)
        if playing >= at_most:
            raise TooManyAtOnce(scope.env, playing)
        placed = CallerJob(
            call=call, org=scope.org, env=scope.env, agent=agent, comparison=comparison, placed_at=parts.store.clock()
        )
        await jobs.add(placed)


async def give_place_back(parts: Harness, call: str) -> None:
    """Give the call's place back: its placing was refused after it took it."""
    async with parts.sessions.begin() as session_:
        await CallerJobRepository(session_).drop(call)


async def count_placed(session_: AsyncSession, scope: Scope) -> int:
    """How many spoken calls of the org hold a place on its line in the env, whichever gateway placed them."""
    return await CallerJobRepository(session_).count_open(scope.org, scope.env)


# In the transaction that makes the call a call (`simulations.place_simulation`): from its commit a
# process may claim the caller, and never one whose call is not there.
async def complete(session_: AsyncSession, simulation: Simulation, named: str) -> None:
    """Say the simulation on the call's row, as it was placed: from here a process may claim it."""
    await CallerJobRepository(session_).complete(simulation.call, dump(simulation, named))


async def list_of_calls(session_: AsyncSession, calls: Sequence[str]) -> dict[str, CallerJob]:
    """Each of these calls' jobs, by its call, for those that have one."""
    return {job.call: job for job in await CallerJobRepository(session_).list_of_calls(calls)}


async def count_open_of(session_: AsyncSession, comparison: str) -> int:
    """How many of the comparison's callers are not over yet."""
    return await CallerJobRepository(session_).count_open_of(comparison)


async def list_lost(session_: AsyncSession, comparison: str) -> Sequence[CallerJob]:
    """The comparison's callers a process left on the line."""
    return await CallerJobRepository(session_).list_lost(comparison)


# ── played by the process that claimed it ──


# What a process does with a caller it claimed, to the end, whatever ends it. Each of the ways out says
# so on the row, which is what every other process and every gateway reads:
# - played, or broken once the call had begun: the job is over, and the call is its agent's to end
#   (the caller's line closes its room as it leaves);
# - broken before the call began: why, for a gateway to end the call with (`settle`);
# - cut while the process stops (a release, the drain run out): a call that never began is let go for
#   another process to play whole; one that had begun is over, said lost, and its comparison places it
#   again.
# A caller claimed a second time (the first process let it go, or stopped) is played only if its call
# still never began: a worker that took the room in between began a call no caller is left on.
async def play_claimed(parts: CallerParts, job: CallerJob, process: str) -> None:
    """Play the caller of a job this process claimed, and say on its row how it left it."""
    call = job.call
    began_without_it = False
    try:
        began_without_it = await _has_begun(parts, call)
        if not began_without_it:
            await play_spoken(parts, load(job))
    except BaseException as broke:
        with survive("saying how a simulated caller was left", call):
            began = await _has_begun(parts, call)
            if is_cancellation(broke):
                await (_let_go(parts, call, process, lost=True) if began else _release(parts, call, process))
            elif began:
                await _let_go(parts, call, process, lost=False)
            else:
                await _say_broke(parts, call, process, say_why(broke, "play this call's caller"))
        raise
    await _let_go(parts, call, process, lost=began_without_it)


async def _has_begun(parts: CallerParts, call: str) -> bool:
    entries = await when_free(lambda: parts.store.whole_of(call))
    return any(entry.type == "call.started" for entry in entries)


async def _let_go(parts: CallerParts, call: str, process: str, *, lost: bool) -> None:
    async def end() -> None:
        async with parts.sessions.begin() as session_:
            await CallerJobRepository(session_).end(call, process, parts.store.clock(), lost=lost)

    await when_free(end)


async def _release(parts: CallerParts, call: str, process: str) -> None:
    async def release() -> None:
        async with parts.sessions.begin() as session_:
            await CallerJobRepository(session_).release(call, process)

    await when_free(release)


async def _say_broke(parts: CallerParts, call: str, process: str, why: str) -> None:
    async def say() -> None:
        async with parts.sessions.begin() as session_:
            await CallerJobRepository(session_).say_broke(call, process, why)

    await when_free(say)


# ── settled by a gateway ──


# What a process that plays callers cannot do, a gateway does, every gateway passing and each row taken
# by the one that finds it: a call that never began is ended by the live side (its reason on its log,
# its end, its summary), which a callers process does not have; and a process that stopped saying it
# plays a caller is not there to say anything else. One connection is held while a call is ended: the
# row is the claim, so no two gateways end one call.
async def settle(parts: Harness) -> None:
    """One pass: end the calls whose caller broke before they began, take up what a process left, clear the old rows."""
    now = parts.store.clock()
    with box_wide():
        for _ in range(SETTLED_A_PASS):
            if not await _end_one_broken(parts, now):
                break
        for _ in range(SETTLED_A_PASS):
            if not await _take_up_one_left(parts, now):
                break
        for _ in range(SETTLED_A_PASS):
            if not await _end_one_nobody_plays(parts, now):
                break
        async with parts.sessions.begin() as session_:
            jobs = CallerJobRepository(session_)
            await jobs.delete_older_than(now - KEPT_AFTER_ITS_END_S, unplaced_before=now - A_PLACING_TAKES_AT_MOST_S)


async def _end_one_broken(parts: Harness, now: float) -> bool:
    async with parts.sessions.begin() as session_:
        job = await CallerJobRepository(session_).find_broken()
        if job is None:
            return False
        with survive("ending a call whose caller broke before it began", job.call):
            await parts.apps.end_never_served(job.call, job.agent, job.broke or "")
        job.ended_at = now
    return True


# The process is gone, with the caller's leg and whatever it had taken on the way: its seat in the
# fleet's line is given back and its room closed, which ends the job of a worker that took it. Then the
# call says which it was: begun, it is over and lost; never begun, it is another process's to play
# whole, once.
async def _take_up_one_left(parts: Harness, now: float) -> bool:
    async with parts.sessions.begin() as session_:
        job = await CallerJobRepository(session_).find_left(now - LEFT_AFTER_S)
        if job is None:
            return False
        logger.warning("%s: the process playing its caller (%s) stopped saying so", job.call, job.claimed_by)
        with survive("taking up a caller its process left", job.call):
            await parts.offering.forget(job.call)
            await close_room(parts.servers[job.env], job.call)
        began = any(entry.type == "call.started" for entry in await parts.store.whole_of(job.call))
        if began:
            job.ended_at, job.lost = now, True
        elif job.played < PLAYED_AT_MOST:
            job.claimed_by, job.heard_at = None, None
        else:
            with survive("ending a call whose caller no process could play", job.call):
                await parts.apps.end_never_served(job.call, job.agent, LEFT_BEFORE_IT_BEGAN)
            job.ended_at, job.lost = now, True
    return True


async def _end_one_nobody_plays(parts: Harness, now: float) -> bool:
    async with parts.sessions.begin() as session_:
        job = await CallerJobRepository(session_).find_unclaimed(now - NOBODY_PLAYS_AFTER_S)
        if job is None:
            return False
        why = NOBODY_PLAYED_IT.format(minutes=NOBODY_PLAYS_AFTER_S / 60)
        with survive("ending a call whose caller no process took", job.call):
            await parts.apps.end_never_served(job.call, job.agent, why)
        job.ended_at = now
    return True
