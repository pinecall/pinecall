"""A comparison's calls placed to its last call's end, by its gateway and by another when that one leaves."""

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass, replace
from functools import partial

from runtime.actor import THE_ORGS_OWN, Actor, Scope
from runtime.billing import service as billing
from runtime.calls import folds
from runtime.calls import service as calls
from runtime.evals.models import CallerJob
from runtime.evals.parts import Harness
from runtime.evals.repository import ComparisonRepository
from runtime.evals.service import caller_jobs, validity
from runtime.evals.service.plans import (
    PICKED_UP_AFTER_S,
    STILL_PLACING_EVERY_S,
    STOPPED,
    Judged,
    Pair,
    Plan,
    Refused,
    actor_of,
    keep_plan,
    read_plan,
    settle_uncounted,
    stop_refused,
)
from runtime.evals.service.simulated_calls import say_why
from runtime.evals.service.simulations import Scenario, as_wanted, place_simulation
from runtime.evals.tasks import TooManyAtOnce
from runtime.exceptions import PinecallError, UpstreamError
from runtime.kit.loops import is_cancellation, survive
from runtime.kit.text import a_mapping
from runtime.livekit import close_room
from runtime.postgres import when_free
from runtime.providers import service as providers
from runtime.scoping import box_wide, within_org
from runtime.wire.base import Entry

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
# Whether a call is still on the line is read this often once every call is placed, so that a command
# following the comparison hears of its end within seconds; the plan is said every STILL_PLACING_EVERY_S.
A_LINE_IS_READ_EVERY_S = 5.0
# The calls that ended are judged this often: one that did not count is placed again, and a vendor that
# refused one for good has its setup rung no more from then on, not once the placing is over.
SWEPT_EVERY_S = 10.0
# What a stage writes when its vendor refused it for good (`session.listener`).
A_DEAD_END = "component_dead_end"
# A refusal's first line names who refused, as `providers.say_failure` says it.
REFUSED_BY = re.compile(r"^(?P<vendor>[\w.-]+) refused ")
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
# has left it, with the calls it was playing and the ones still to place, and another takes it up. The
# calls that ended are judged as it goes: one that did not count is placed again, and a setup whose
# vendor refused for good is rung no more.
async def play_to_the_end(
    parts: Harness, plan: Plan, waiting: Sequence[Pair], place: Callable[[Pair], Awaitable[object]]
) -> None:
    """Place what waits, say the comparison is played until its last call ended, then say it done."""
    clock = parts.store.clock
    # The calls judged and found to count: a caller's line is kept before its job is over, so it is final.
    counted: set[str] = set()
    swept_at = clock()

    async def say() -> None:
        await keep_plan(parts.sessions, plan)

    def is_time_to_sweep() -> bool:
        nonlocal swept_at
        if clock() - swept_at < SWEPT_EVERY_S:
            return False
        swept_at = clock()
        return True

    # While calls still wait for a place, a vendor that refused one of the calls that ended stops its
    # setup: the ones behind it are refused as they come up, and spend nothing.
    async def say_and_stop() -> None:
        if is_time_to_sweep():
            stop_refused(plan, (await when_free(lambda: judge_ended(parts, plan, counted))).judged)
        await say()

    async def place_again() -> bool:
        left = await _place_again_what_a_process_left(parts, plan, rung, say)
        return await _place_again_what_did_not_count(parts, plan, rung, say, counted) or left

    async def wait_for_the_line(*, sweeping: bool) -> None:
        while await when_free(lambda: _is_any_on_the_line(parts, plan)):
            await asyncio.sleep(A_LINE_IS_READ_EVERY_S)
            if clock() - plan.heard_at >= STILL_PLACING_EVERY_S:
                plan.heard_at = clock()
                await when_free(say)
            if sweeping and is_time_to_sweep():
                await place_again()

    rung = refusing_what_stopped(plan, place)
    # A gateway that stops saying so has its comparison taken up by another, which ends the calls it
    # finds on the line and places them again: a pool full for two seconds is no reason to stop saying.
    await place_waiting(plan, waiting, rung, say_and_stop, clock=clock)
    await wait_for_the_line(sweeping=True)
    # A call may be lost, or end without counting, as the last one ends: looked for once more before
    # the comparison is said done.
    while await place_again():
        await wait_for_the_line(sweeping=False)
    plan.done = True
    plan.heard_at = clock()
    await when_free(say)


# A spoken call's caller is played by a process that may stop under it (a release that outlasts its
# drain, a crash): the call is over then, its caller not played whole, and its job's row says so
# (`caller_jobs`). It stands for nothing in the table, as a call lost with its gateway does not, and
# is placed again.
async def _place_again_what_a_process_left(
    parts: Harness, plan: Plan, place: Callable[[Pair], Awaitable[object]], say: Callable[[], Awaitable[None]]
) -> bool:
    async def read() -> list[tuple[str, Pair]]:
        async with parts.sessions.begin() as session_:
            lost = await caller_jobs.list_lost(session_, plan.comparison)
        settled = set(plan.replaced) | {one.call for one in plan.uncounted}
        return [(job.call, Pair(*caller_jobs.pair_of(job))) for job in lost if job.call not in settled]

    lost = await when_free(read)
    if not lost:
        return False
    plan.replaced += [call for call, _ in lost]
    plan.waiting = len(lost)
    plan.heard_at = parts.store.clock()
    await when_free(say)
    await place_waiting(plan, [pair for _, pair in lost], place, say, clock=parts.store.clock)
    return True


# ── a call that did not count ──


@dataclass(frozen=True, slots=True)
class Ended:
    """The comparison's calls that ended and were not judged yet, and how many more it may place."""

    judged: list[Judged]
    room: int
    most: int


# A call that did not count (`validity`) stands for nothing in the table: it stays a row, marked, and
# its place is placed again, a bounded number of times, or refused saying why (`plans.settle_uncounted`).
# On 2026-11-26 a comparison of 140 calls ended with 19 that did not count (a vendor out of credit, a
# vendor's 504, two callers' own voices) and its table short of them; fourteen were placed by hand.
async def _place_again_what_did_not_count(
    parts: Harness,
    plan: Plan,
    place: Callable[[Pair], Awaitable[object]],
    say: Callable[[], Awaitable[None]],
    counted: set[str],
) -> bool:
    ended = await when_free(lambda: judge_ended(parts, plan, counted))
    settled = len(plan.uncounted)
    again = settle_uncounted(plan, ended.judged, room=ended.room, most=ended.most)
    if len(plan.uncounted) == settled:
        return False
    plan.waiting = len(again)
    plan.heard_at = parts.store.clock()
    await when_free(say)
    if again:
        await place_waiting(plan, again, place, say, clock=parts.store.clock)
    return bool(again)


# A spoken call's caller keeps how its own line went before its job is over (`simulated_calls`), so a
# call is judged once its job is: before that its line is not known, and a call that counts then
# counts for good. A call its process left is the other's to place again (`list_lost`).
async def judge_ended(parts: Harness, plan: Plan, counted: set[str]) -> Ended:
    """Judge the calls that ended and are not settled: whether each counted, and a vendor's refusal for good."""
    settled = set(plan.replaced) | {one.call for one in plan.uncounted} | counted
    async with parts.sessions.begin() as session_:
        asked = calls.PersonaRunFilters(comparison=plan.comparison, holders=None)
        found = await calls.list_persona_runs(session_, plan.scope, asked, limit=CALLS_READ_AT_MOST)
        ended = [run for run in found.runs if run.facts.ended_at is not None and run.facts.call not in settled]
        jobs = await caller_jobs.list_of_calls(session_, [run.facts.call for run in ended])
        ready = [run for run in ended if _is_over(jobs.get(run.facts.call))]
        errors = await calls.list_errors(session_, [run.facts.call for run in ready])
        most = (await billing.get_quotas(session_, plan.scope.org, plan.scope.env)).compared_at_most
    judged: list[Judged] = []
    for run in ready:
        facts = folds.facts_of(run.facts)
        said = errors.get(facts.call, [])
        judgement = validity.judge(said, facts.end_reason, run.facts.caller_line)
        if judgement.valid:
            counted.add(facts.call)
            continue
        for_good, unpaid = refusal_for_good(said)
        pair = Pair(facts.persona or "", dict(run.facts.against or {}))
        judged.append(Judged(facts.call, pair, judgement, for_good=for_good, unpaid=unpaid))
    return Ended(judged, room=max(0, most - len(found.runs)), most=most)


def _is_over(job: CallerJob | None) -> bool:
    return job is None or (job.ended_at is not None and not job.lost)


# A stage that ended the call for good (a key, a model, an account with no credit) writes a dead end;
# a realtime model's refusal for payment reaches the log as words alone, its vendor's code among them.
def refusal_for_good(errors: Iterable[Entry]) -> tuple[bool, str]:
    """Whether a vendor refused the call in a way no retry changes, and the vendor when its account cannot pay."""
    for entry in errors:
        code, message = str(entry.data.get("code") or ""), str(entry.data.get("message") or "")
        if code not in validity.OF_A_VENDOR:
            continue
        unpaid = providers.says_unpaid(message)
        if code == A_DEAD_END or unpaid:
            named = REFUSED_BY.match(message)
            vendor = providers.vendor_named_in(message) or ("" if named is None else named["vendor"])
            return True, vendor if unpaid else ""
    return False, ""


# A setup a vendor refused for good is not rung again: its calls are refused in that vendor's words as
# they come to be placed, and spend nothing.
def refusing_what_stopped(
    plan: Plan, place: Callable[[Pair], Awaitable[object]]
) -> Callable[[Pair], Awaitable[object]]:
    """How a call of the comparison is placed, refused instead when its setup was stopped."""

    async def rung(pair: Pair) -> object:
        stopped = plan.find_stop(pair.against)
        if stopped is not None:
            raise UpstreamError(STOPPED.format(why=stopped.why))
        return await place(pair)

    return rung


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


# A call whose caller was a task of the gateway that left (a written call, and every call a gateway
# of the release before 2026-11-25 placed) went with it when it had not ended as that gateway last
# said the comparison was played: the one that never began is ended, saying why, the one on the line
# has its room closed, which ends it and frees its seat, and each is placed again. A call that ended in
# the seconds after is placed again too: that it was played whole is not known. A spoken call's caller
# is a job of a process, which the gateway leaving changes nothing for: the call stands for its place
# in the table whatever it is doing, unless its own process left it, which its row says.
async def take_up(parts: Harness, plan: Plan, last_said: float) -> None:
    """Go on with a comparison another gateway left: place again what was lost with it, then the rest."""
    scope = plan.scope
    async with parts.sessions.begin() as session_:
        asked = calls.PersonaRunFilters(comparison=plan.comparison, holders=None)
        found = await calls.list_persona_runs(session_, scope, asked, limit=CALLS_READ_AT_MOST)
        jobs = await caller_jobs.list_of_calls(session_, [run.facts.call for run in found.runs])
    played: list[Pair] = []
    # A call that did not count stands for no place: the one placed in its stead does, or its refusal.
    settled = set(plan.replaced) | {one.call for one in plan.uncounted}
    for run in found.runs:
        facts = folds.facts_of(run.facts)
        if facts.call in settled:
            continue
        job = jobs.get(facts.call)
        if job is not None:
            if job.lost:
                plan.replaced.append(facts.call)
            else:
                played.append(Pair(facts.persona or "", dict(run.facts.against or {})))
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


# A spoken call is a run of the table once a worker opened it, and its caller may wait before that: for
# a process to claim it, then for a seat of the fleet, three quarters of an hour at most. Its job's row
# says so from the moment it is placed. Until 2026-11-25 a comparison whose calls all waited read as
# having none on the line, and was said done with calls still to be played.
async def _is_any_on_the_line(parts: Harness, plan: Plan) -> bool:
    async with parts.sessions.begin() as session_:
        if await caller_jobs.count_open_of(session_, plan.comparison) > 0:
            return True
        asked = calls.PersonaRunFilters(comparison=plan.comparison, holders=None)
        found = await calls.list_persona_runs(session_, plan.scope, asked, limit=CALLS_READ_AT_MOST)
    return any(run.facts.call not in plan.replaced and folds.facts_of(run.facts).ended_at is None for run in found.runs)
