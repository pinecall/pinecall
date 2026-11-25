"""A comparison: a persona or more against the agent under several voices and models, its calls read side by side."""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from statistics import median
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.actor import Actor, Scope
from runtime.billing import service as billing
from runtime.calls import folds
from runtime.calls import service as calls
from runtime.calls.log import Store
from runtime.evals.parts import Harness
from runtime.evals.repository import ComparisonRepository
from runtime.evals.service.placing import place_as_planned, play_to_the_end
from runtime.evals.service.plans import Pair, Plan, Refused, is_left, keep_plan, read_plan, say_who_asked
from runtime.evals.service.simulated_calls import Scored, score_of
from runtime.evals.service.simulations import Scenario, Wanted, as_placed, check_talking, write_scenario
from runtime.evals.tasks import TooManyAtOnce
from runtime.exceptions import NotFound, PinecallError, ValidationError
from runtime.kit.crypto import random_id
from runtime.kit.text import JsonObject
from runtime.postgres import DatabaseError, is_pool_timeout, when_free
from runtime.wire.base import Entry
from runtime.wire.parts import ScoreVerdict
from runtime.wire.scores import CallScore
from runtime.wire.state import AgentTurn

# The most rows a comparison's table reads: past any org's `comparison_calls`.
ROWS_READ_AT_MOST = 500
COMPARISON_PREFIX = "cmp_"
# The turn measures a row carries, each its median over the call (`calls.folds`).
MEASURES = ("e2e_latency", "llm_node_ttft", "tts_node_ttfb", "transcription_delay", "end_of_turn_delay")
# The judge that holds a call to what its caller expected of the agent: a comparison's task is done by it.
THE_GOAL = "expected-outcome"
SCORED = "call.score"


@dataclass(frozen=True, slots=True)
class Verdict:
    """One judge's answer on one call of a comparison: its name, what it said, and why."""

    name: str
    verdict: ScoreVerdict
    reason: str


@dataclass(frozen=True, slots=True)
class Row:
    """One call of a comparison: the caller, what the agent ran on, how it went, what it cost, how fast it was."""

    call: str
    persona: str
    against: Mapping[str, Any]
    started_at: float
    ended_at: float | None
    turns: int
    end_reason: str | None
    score: Scored | None
    cost_usd: float | None
    # Each measure's median in seconds over the call's turns; one no turn reported is None.
    latency: Mapping[str, float | None]
    # Why the call ended before it began (a vendor that refused its stage), from the log's `error`.
    why: str | None
    # Whether the caller got what it expected of the agent, as the judge of its expectations answered.
    goal: ScoreVerdict | None
    # Each judge's answer, in the order the panel asked them; empty until the call is scored.
    judges: tuple[Verdict, ...]
    # The agent's replies, the slowest of them end to end in seconds, and how many the caller cut off.
    replies: int
    slowest_reply: float | None
    cut_off: int
    # How the call was heard, against what its caller really said; None for a written call.
    hearing: Mapping[str, Any] | None


@dataclass(frozen=True, slots=True)
class PlacedCall:
    """One call a comparison placed: the caller, what the agent runs on, and the call."""

    persona: str
    against: JsonObject
    call: str


@dataclass(frozen=True, slots=True)
class Begun:
    """A comparison started: its id, each call placed, what was refused, and how many wait for a place."""

    comparison: str
    spoken: bool
    calls: list[PlacedCall]
    refused: list[Refused]
    waiting: int


@dataclass(frozen=True, slots=True)
class Compared:
    """A comparison read: what was asked for, how its placing stands, and its calls, each caller's best first."""

    plan: Plan
    rows: list[Row]
    planned: int
    abandoned: bool


# ── started ──


# Each call is placed as one simulation is, under one id they share: every caller against every
# configuration, as many times as asked. The ones the org's line has room for are placed before the
# answer; the rest wait their turn and are placed by this gateway as the ones before them end, the
# comparison's row saying how many still wait. One refused (a vendor nobody keyed, the org's limits)
# is said beside the ones that started, which go on. A caller is briefed once for the whole
# comparison: until 2026-11 each call was briefed on its own, so every configuration conversed about
# something else, and a scenario the request brought for its first caller was given to every one.
async def start_comparison(
    parts: Harness, actor: Actor, wanted: Wanted, against: Sequence[JsonObject], personas: Sequence[str], repeats: int
) -> Begun:
    """Each persona against the agent under each voice and models named, as many times as asked; what started."""
    async with parts.sessions.begin() as session_:
        quotas = await billing.get_quotas(session_, actor.org, actor.env)
    asked = len(personas) * len(against) * repeats
    if asked > quotas.compared_at_most:
        raise ValidationError(
            f"a comparison of this org places {quotas.compared_at_most} calls at most: {len(personas)} callers "
            f"against {len(against)} configurations, {repeats} times each, is {asked}"
        )
    for values in against:
        await check_talking(parts, actor.scope, values, spoken=wanted.spoken)
    briefed = await _brief_each(parts, actor, wanted, list(personas))
    plan = Plan(
        comparison=random_id(COMPARISON_PREFIX, 6),
        agent=wanted.agent,
        scope=actor.scope,
        spoken=wanted.spoken,
        personas=list(personas),
        against=[dict(values) for values in against],
        repeats=repeats,
        started_at=parts.store.clock(),
        wanted=as_placed(wanted),
        briefs={
            persona: None if brief is None else {"goal": brief.goal, "facts": dict(brief.facts)}
            for persona, brief in briefed.items()
            if not isinstance(brief, PinecallError)
        },
        by=say_who_asked(actor),
        done=False,
    )
    as_planned = place_as_planned(parts, actor, plan)

    async def place(pair: Pair) -> str:
        unbriefed = briefed[pair.persona]
        if isinstance(unbriefed, PinecallError):
            raise unbriefed
        return await as_planned(pair)

    placed: list[PlacedCall] = []
    waiting: list[Pair] = []
    for pair in plan.list_pairs():
        # Once one waits for a place, every one after it waits behind it: the order asked for is kept.
        if waiting:
            waiting.append(pair)
            continue
        try:
            call = await place(pair)
        except TooManyAtOnce:
            waiting.append(pair)
            continue
        except PinecallError as why:
            plan.refused.append(Refused(pair.persona, pair.against, str(why)))
            continue
        except DatabaseError as full:
            # No connection for it now: it waits its turn with the ones behind it, and the placing that
            # follows the answer asks the database again. Answered "busy" here, the request would leave
            # the calls it had placed with no plan to count them in.
            if not is_pool_timeout(full):
                raise
            waiting.append(pair)
            continue
        placed.append(PlacedCall(pair.persona, pair.against, call))
    plan.waiting = len(waiting)
    plan.heard_at = parts.store.clock()
    await when_free(lambda: keep_plan(parts.sessions, plan))
    # Played by this gateway to its last call's end, whether or not a call waits: it says so as it
    # goes, and a gateway that stops saying so has its comparison taken up by another (`placing`).
    parts.simulations.place_later(play_to_the_end(parts, plan, waiting, place))
    return Begun(plan.comparison, wanted.spoken, placed, list(plan.refused), len(waiting))


# ── read ──


async def get_comparison(session_: AsyncSession, parts: Harness, actor: Actor, comparison: str) -> Compared:
    """The comparison's calls, each caller's best first: its goal held, every judge, the fastest, the cheapest."""
    wanted = calls.PersonaRunFilters(comparison=comparison, holders=calls.list_copies(actor))
    found = await calls.list_persona_runs(session_, actor.scope, wanted, limit=ROWS_READ_AT_MOST)
    rows = [await compare_row(parts.store, run) for run in found.runs]
    plan = await plan_of(session_, actor.scope, comparison, found.runs, rows)
    # A call lost with its gateway was placed again: the one that stands for it is the row.
    rows = [row for row in rows if row.call not in plan.replaced]
    planned = plan.planned if plan.kept else len(rows)
    return Compared(plan, rank(rows), planned, abandoned=plan.kept and is_left(plan, parts.store.clock()))


# What was asked for names the callers before any of them has a call. A comparison made before plans
# were kept has no row: it is what its calls say (its callers in the order placed, one repeat, nothing
# waiting). Until 2026-11 the endpoint asked "is there a plan" nine times in a row.
async def plan_of(
    session_: AsyncSession, scope: Scope, comparison: str, runs: Sequence[calls.PersonaRun], rows: Sequence[Row]
) -> Plan:
    """The comparison as it was asked for: the plan kept, or the one its calls say; refused when it has neither."""
    kept = await ComparisonRepository(session_).find(scope.org, scope.env, comparison)
    if kept is not None:
        return read_plan(kept, scope)
    if not runs:
        raise NotFound(f"no comparison {comparison} in this key's org and env")
    return Plan(
        comparison=comparison,
        agent=runs[0].agent,
        scope=scope,
        spoken=folds.facts_of(runs[0].facts).spoken,
        personas=list_in_order_placed(rows),
        against=[],
        repeats=1,
        started_at=min(run.started_at for run in runs),
        kept=False,
    )


async def compare_row(store: Store, run: calls.PersonaRun) -> Row:
    """One call of the comparison as its row: what the agent ran on, how it went, its cost, its latencies."""
    facts = folds.facts_of(run.facts)
    entries = list(await store.whole_of(facts.call))
    judges = list_verdicts(entries)
    replies = [turn for turn in folds.reduce(entries).turns if isinstance(turn, AgentTurn)]
    answered = [turn.metrics.e2e_latency for turn in replies if turn.metrics.e2e_latency is not None]
    return Row(
        call=facts.call,
        persona=facts.persona or "",
        against=dict(run.facts.against or {}),
        started_at=run.started_at,
        ended_at=facts.ended_at,
        turns=len(facts.heard_at),
        end_reason=facts.end_reason,
        score=score_of(facts),
        cost_usd=facts.cost_usd,
        latency=latency_of(entries),
        why=find_why_it_never_began(entries),
        goal=goal_of(judges),
        judges=tuple(judges),
        replies=len(replies),
        slowest_reply=max(answered, default=None),
        cut_off=len([turn for turn in replies if turn.interrupted]),
        hearing=run.facts.hearing,
    )


# A judge that was deferred or skipped never answered: it is no verdict on the call.
def list_verdicts(entries: Iterable[Entry]) -> list[Verdict]:
    """What each judge answered on the call, from its score; none before it is scored."""
    scored = [entry for entry in entries if entry.type == SCORED]
    if not scored:
        return []
    answered = CallScore.model_validate(scored[-1].data).judges
    return [
        Verdict(judge.name, judge.verdict, judge.reason)
        for judge in answered
        if judge.verdict not in ("deferred", "skipped")
    ]


def goal_of(judges: Sequence[Verdict]) -> ScoreVerdict | None:
    """Whether the caller got what it expected, as its judge answered; None when that judge said nothing."""
    return next((judge.verdict for judge in judges if judge.name == THE_GOAL), None)


def find_why_it_never_began(entries: Iterable[Entry]) -> str | None:
    """The reason a call ended before it began, from its log's unrecoverable error; None for one that ran."""
    for entry in entries:
        if entry.type == "error" and entry.data.get("recoverable") is False:
            return str(entry.data.get("message") or "")
        if entry.type == "call.started":
            return None
    return None


def latency_of(entries: Iterable[Entry]) -> dict[str, float | None]:
    """Each measure's median over the call's turns; one no turn reported is None."""
    samples = folds.samples(folds.reduce(entries).turns)
    return {name: median(samples[name]) if samples.get(name) else None for name in MEASURES}


def list_in_order_placed(rows: Sequence[Row]) -> list[str]:
    """The comparison's callers, each once, in the order their calls were placed."""
    return list(dict.fromkeys(row.persona for row in sorted(rows, key=lambda row: row.started_at)))


# The best is the one a person would pick first: the caller got what it expected, then every judge
# held, then the most that held, then the fastest reply, then the cheapest. A caller that expects
# nothing has no goal to be judged on: its call is done when every judge held. A call still on the
# line is last: nothing of it is known yet.
def is_done(row: Row) -> bool:
    """Whether the call did its caller's task: its goal held, or, with no goal judged, every judge did."""
    if row.goal is not None:
        return row.goal == "held"
    return row.score is not None and row.score.passed


# Each caller's rows together, the callers in the order placed, so a table reads one caller at a time.
def rank(rows: Sequence[Row]) -> list[Row]:
    """The rows best first, caller by caller."""
    order = {persona: at for at, persona in enumerate(list_in_order_placed(rows))}

    def key(row: Row) -> tuple[int, bool, bool, bool, float, float, float]:
        judged = row.score is not None and row.score.judged > 0
        passed = row.score is not None and row.score.passed
        share = row.score.held / row.score.judged if judged and row.score is not None else 0.0
        e2e = row.latency.get("e2e_latency")
        cost = row.cost_usd if row.cost_usd is not None else float("inf")
        fastest = e2e if e2e is not None else float("inf")
        return (order[row.persona], row.ended_at is None, not is_done(row), not passed, -share, fastest, cost)

    return sorted(rows, key=key)


# The scenario the request brought is its first caller's; every other caller of the library is briefed
# on the agent, once. A caller that could not be briefed (the org out of evals) is refused in each of
# its calls, with that sentence.
async def _brief_each(
    parts: Harness, actor: Actor, wanted: Wanted, personas: Sequence[str]
) -> dict[str, Scenario | PinecallError | None]:
    briefed: dict[str, Scenario | PinecallError | None] = {}
    for persona in personas:
        if persona == wanted.persona and wanted.scenario is not None:
            briefed[persona] = wanted.scenario
            continue
        try:
            briefed[persona] = await write_scenario(parts, actor.scope, replace(wanted, persona=persona, scenario=None))
        except PinecallError as refused:
            briefed[persona] = refused
    return briefed
