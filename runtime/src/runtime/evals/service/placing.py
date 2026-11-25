"""A comparison's calls placed to its last call's end, by its gateway and by another when that one leaves."""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import replace
from functools import partial

from runtime.actor import THE_ORGS_OWN, Actor, Scope
from runtime.calls import folds
from runtime.calls import service as calls
from runtime.evals.parts import Harness
from runtime.evals.repository import ComparisonRepository
from runtime.evals.service.plans import (
    PICKED_UP_AFTER_S,
    STILL_PLACING_EVERY_S,
    Pair,
    Plan,
    Refused,
    actor_of,
    keep_plan,
    read_plan,
)
from runtime.evals.service.simulated_calls import say_why
from runtime.evals.service.simulations import Scenario, as_wanted, place_simulation
from runtime.evals.tasks import TooManyAtOnce
from runtime.exceptions import PinecallError
from runtime.kit.loops import is_cancellation, survive
from runtime.kit.text import a_mapping
from runtime.livekit import close_room
from runtime.postgres import when_free
from runtime.scoping import box_wide, within_org

logger = logging.getLogger(__name__)

# A call that waits for a place on the line asks again this often.
A_PLACE_IS_ASKED_EVERY_S = 2.0
# A comparison whose calls never get a place stops asking: the org's line is held by something else.
PLACING_GIVES_UP_AFTER_S = 45 * 60.0
NEVER_GOT_A_PLACE = (
    "no place on the line in {minutes:.0f} minutes: the org's simulated calls never went under its most at once"
)
# The most calls a comparison's table reads: past any org's `comparison_calls`.
CALLS_READ_AT_MOST = 500
LOST_WITH_ITS_GATEWAY = (
    "the gateway that played this call's caller was started again before the call began: the comparison places it again"
)


# A place on the line is the org's own ceiling, so it is waited for; anything else that refuses a
# call (a vendor nobody keyed, the month's simulations used up) would refuse it again a second later.
# Every call asked for ends as one of three things a reader can count: a call, a call that waits, or a
# refusal with its reason. A placing that found the pool full is asked again (`when_free`) and refused
# as busy past that; one that broke some other way is refused by the kind of what broke, and the ones
# behind it go on. Until 2026-11-25 either one ended this task: the calls behind it were never placed,
# and the plan went on saying none waited and none was refused.
async def place_waiting(
    plan: Plan,
    waiting: Sequence[Pair],
    place: Callable[[Pair], Awaitable[object]],
    say: Callable[[], Awaitable[None]],
    *,
    clock: Callable[[], float],
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    """Place each call that waits as a place on the line frees, saying how the placing stands as it goes."""
    began = clock()
    left = list(waiting)

    async def tell() -> None:
        await when_free(say, clock=clock, sleep=sleep)

    while left:
        pair = left[0]
        try:
            await when_free(partial(place, pair), clock=clock, sleep=sleep)
        except TooManyAtOnce:
            waited = clock() - began
            if waited >= PLACING_GIVES_UP_AFTER_S:
                why = NEVER_GOT_A_PLACE.format(minutes=waited / 60)
                plan.refused += [Refused(one.persona, one.against, why) for one in left]
                left = []
            elif clock() - plan.heard_at >= STILL_PLACING_EVERY_S:
                plan.heard_at = clock()
                await tell()
            if left:
                await sleep(A_PLACE_IS_ASKED_EVERY_S)
            continue
        except PinecallError as why:
            plan.refused.append(Refused(pair.persona, pair.against, str(why)))
        except Exception as broke:
            if is_cancellation(broke):
                raise
            logger.warning("%s: a call of %s could not be placed", plan.comparison, pair.persona, exc_info=broke)
            plan.refused.append(Refused(pair.persona, pair.against, say_why(broke, "place this call")))
        left.pop(0)
        plan.waiting = len(left)
        plan.heard_at = clock()
        await tell()
    plan.waiting = 0
    plan.heard_at = clock()
    await tell()


# ── from the request to the last call's end ──


# Every call of a comparison is placed from its plan alone: what the request said (`wanted`), each
# caller's brief and the key that asked. The gateway that took the request and the one that takes the
# comparison up after it place the same call.
def place_as_planned(parts: Harness, actor: Actor, plan: Plan) -> Callable[[Pair], Awaitable[str]]:
    """How one call of the comparison is placed: the caller under the agent's values, on a call of its own."""

    async def place(pair: Pair) -> str:
        brief = plan.briefs.get(pair.persona)
        scenario = None if brief is None else Scenario(str(brief["goal"]), dict(brief["facts"]))
        one = replace(as_wanted(plan.agent, pair.persona, plan.wanted or {}), scenario=scenario)
        started = await place_simulation(parts, actor, one, against=dict(pair.against), comparison=plan.comparison)
        return started.call

    return place


# The comparison says it is played for as long as one of its calls is: a gateway that stops saying so
# has left it, with the calls it was playing and the ones still to place, and another takes it up.
async def play_to_the_end(
    parts: Harness, plan: Plan, waiting: Sequence[Pair], place: Callable[[Pair], Awaitable[object]]
) -> None:
    """Place what waits, say the comparison is played until its last call ended, then say it done."""

    async def say() -> None:
        await keep_plan(parts.sessions, plan)

    # A gateway that stops saying so has its comparison taken up by another, which ends the calls it
    # finds on the line and places them again: a pool full for two seconds is no reason to stop saying.
    await place_waiting(plan, waiting, place, say, clock=parts.store.clock)
    while await when_free(lambda: _is_any_on_the_line(parts, plan)):
        await asyncio.sleep(STILL_PLACING_EVERY_S)
        plan.heard_at = parts.store.clock()
        await when_free(say)
    plan.done = True
    plan.heard_at = parts.store.clock()
    await when_free(say)


# ── taken up ──


# Every gateway passes, a comparison a pass: the one that finds a row holds it for the transaction it
# writes "I have it" in, and the others skip it. The comparison then goes on as a task of this
# gateway, named for its org as the request that began it was.
async def take_up_left(parts: Harness) -> None:
    """Take up one comparison its gateway left: its lost calls placed again, the rest placed, played to its end."""
    now = parts.store.clock()
    async with parts.sessions.begin() as session_:
        with box_wide():
            row = await ComparisonRepository(session_).find_left(now - PICKED_UP_AFTER_S)
            if row is None:
                return
            by = row.document.get("by")
            holder = str(by.get("holder") or THE_ORGS_OWN) if a_mapping(by) else THE_ORGS_OWN
            plan = read_plan(row, Scope(row.org, row.env, holder))
            last_said = plan.heard_at
            row.document = {**row.document, "heard_at": now}
    plan.heard_at = now
    with within_org(plan.scope.org):
        parts.simulations.place_later(take_up(parts, plan, last_said))


# A call that had not ended when its gateway last said the comparison was played went with that
# gateway, its caller a task of the process: the one that never began is ended, saying why, the one
# on the line has its room closed, which ends it and frees its seat, and each is placed again. A call
# that ended in the seconds after is placed again too: that it was played whole is not known.
async def take_up(parts: Harness, plan: Plan, last_said: float) -> None:
    """Go on with a comparison another gateway left: place again what was lost with it, then the rest."""
    scope = plan.scope
    async with parts.sessions.begin() as session_:
        asked = calls.PersonaRunFilters(comparison=plan.comparison, holders=None)
        found = await calls.list_persona_runs(session_, scope, asked, limit=CALLS_READ_AT_MOST)
    played: list[Pair] = []
    for run in found.runs:
        facts = folds.facts_of(run.facts)
        if facts.call in plan.replaced:
            continue
        if facts.ended_at is not None and facts.ended_at <= last_said:
            played.append(Pair(facts.persona or "", dict(run.facts.against or {})))
            continue
        with survive("ending a call lost with the gateway that played it", facts.call):
            if facts.ended_at is None:
                await _end_lost(parts, plan, facts.call)
        plan.replaced.append(facts.call)
    left = list_left_to_place(plan, played)
    plan.waiting = len(left)
    await keep_plan(parts.sessions, plan)
    await play_to_the_end(parts, plan, left, place_as_planned(parts, actor_of(plan), plan))


def list_left_to_place(plan: Plan, played: Sequence[Pair]) -> list[Pair]:
    """The calls of the plan no call stands for yet, in the order asked: neither played nor refused."""
    stand = [*played, *(Pair(one.persona, one.against) for one in plan.refused)]
    left: list[Pair] = []
    for pair in plan.list_pairs():
        if pair in stand:
            stand.remove(pair)
        else:
            left.append(pair)
    return left


async def _end_lost(parts: Harness, plan: Plan, call: str) -> None:
    await parts.offering.forget(call)
    if any(entry.type == "call.started" for entry in await parts.store.whole_of(call)):
        await close_room(parts.servers[plan.scope.env], call)
    else:
        await parts.apps.end_never_served(call, plan.agent, LOST_WITH_ITS_GATEWAY)


async def _is_any_on_the_line(parts: Harness, plan: Plan) -> bool:
    async with parts.sessions.begin() as session_:
        asked = calls.PersonaRunFilters(comparison=plan.comparison, holders=None)
        found = await calls.list_persona_runs(session_, plan.scope, asked, limit=CALLS_READ_AT_MOST)
    return any(run.facts.call not in plan.replaced and folds.facts_of(run.facts).ended_at is None for run in found.runs)
