"""A comparison: a persona or more against the agent under several voices and models, its calls read side by side."""

import asyncio
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass, field
from statistics import median
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.billing import service as billing
from pinecall_runtime.calls import service as calls
from pinecall_runtime.evals.repository import ComparisonRepository
from pinecall_runtime.evals.schemas import ComparedRefusal, ComparisonRow, Latency, RowVerdict, SessionScore
from pinecall_runtime.evals.service.simulations import TooManyAtOnce
from pinecall_runtime.exceptions import PinecallError
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.wire.base import Entry
from pinecall_runtime.wire.parts import ScoreVerdict
from pinecall_runtime.wire.scores import CallScore
from pinecall_runtime.wire.state import AgentTurn

# The calls one comparison places for an org nobody gave another number (its quotas' `comparison_calls`).
COMPARED_AT_MOST = billing.COMPARISON_CALLS
TOO_MANY_COMPARED = (
    "a comparison of this org places {most} calls at most: {personas} callers against {configs} "
    "configurations, {repeats} times each, is {calls}"
)
# The most rows a comparison's table reads: past any org's `comparison_calls`.
ROWS_READ_AT_MOST = 500
# A call that waits for a place on the line asks again this often, and the comparison says it is
# still being placed this often: one that has not said so for three of them was left by its gateway.
A_PLACE_IS_ASKED_EVERY_S = 2.0
STILL_PLACING_EVERY_S = 20.0
LEFT_AFTER_S = 3 * STILL_PLACING_EVERY_S
# A comparison whose calls never get a place stops asking: the org's line is held by something else.
PLACING_GIVES_UP_AFTER_S = 45 * 60.0
NEVER_GOT_A_PLACE = (
    "no place on the line in {minutes:.0f} minutes: the org's simulated calls never went under its most at once"
)
COMPARISON_PREFIX = "cmp_"
NO_SUCH_COMPARISON = "no comparison {comparison} in this key's org and env"
# The turn measures a row carries, each its median over the call (calls/latencies.py).
MEASURES = ("e2e_latency", "llm_node_ttft", "tts_node_ttfb", "transcription_delay", "end_of_turn_delay")
# The judge that holds a call to what its caller expected of the agent: a comparison's task is done by it.
THE_GOAL = "expected-outcome"
SCORED = "call.score"


async def compared_row(serving: calls.Serving, run: calls.PersonaRun) -> ComparisonRow:
    """One call of the comparison as its row: what the agent ran on, how it went, its cost, its latencies."""
    facts = calls.facts_of(run.facts)
    entries = list(await serving.logs.store.whole(facts.call))
    judges = verdicts_of(entries)
    replies = [turn for turn in calls.reduce(entries).turns if isinstance(turn, AgentTurn)]
    answered = [turn.metrics.e2e_latency for turn in replies if turn.metrics.e2e_latency is not None]
    score = None
    if facts.judged is not None and facts.passed is not None:
        score = SessionScore(held=facts.held or 0, judged=facts.judged, passed=facts.passed, reason=facts.reason)
    return ComparisonRow.model_validate(
        {
            "call": facts.call,
            "persona": facts.persona or "",
            "against": dict(facts.against or {}),
            "started_at": run.started_at,
            "ended_at": facts.ended_at,
            "turns": len(facts.heard_at),
            "end_reason": facts.end_reason,
            "score": None if score is None else score.dump(),
            "cost_usd": facts.cost_usd,
            "latency": latency_of(entries).model_dump(),
            "why": why_it_never_began(entries),
            "goal": goal_of(judges),
            "judges": [judge.model_dump() for judge in judges],
            "replies": len(replies),
            "slowest_reply": max(answered, default=None),
            "cut_off": len([turn for turn in replies if turn.interrupted]),
            "hearing": facts.hearing,
        }
    )


# A judge that was deferred or skipped never answered: it is no verdict on the call.
def verdicts_of(entries: Iterable[Entry]) -> list[RowVerdict]:
    """What each judge answered on the call, from its score; none before it is scored."""
    scored = [entry for entry in entries if entry.type == SCORED]
    if not scored:
        return []
    answered = CallScore.model_validate(scored[-1].data).judges
    return [
        RowVerdict(name=judge.name, verdict=judge.verdict, reason=judge.reason)
        for judge in answered
        if judge.verdict not in ("deferred", "skipped")
    ]


def goal_of(judges: Sequence[RowVerdict]) -> ScoreVerdict | None:
    """Whether the caller got what it expected, as its judge answered; None when that judge said nothing."""
    return next((judge.verdict for judge in judges if judge.name == THE_GOAL), None)


def why_it_never_began(entries: Iterable[Entry]) -> str | None:
    """The reason a call ended before it began, from its log's unrecoverable error; None for one that ran."""
    for entry in entries:
        if entry.type == "error" and entry.data.get("recoverable") is False:
            return str(entry.data.get("message") or "")
        if entry.type == "call.started":
            return None
    return None


def latency_of(entries: Iterable[Entry]) -> Latency:
    """Each measure's median over the call's turns; one no turn reported is None."""
    samples = calls.samples(calls.reduce(entries).turns)
    return Latency(**{name: median(samples[name]) if name in samples else None for name in MEASURES})


def in_the_order_placed(rows: Sequence[ComparisonRow]) -> list[str]:
    """The comparison's callers, each once, in the order their calls were placed."""
    return list(dict.fromkeys(row.persona for row in sorted(rows, key=lambda row: row.started_at)))


# The best is the one a person would pick first: the caller got what it expected, then every judge
# held, then the most that held, then the fastest reply, then the cheapest. A caller that expects
# nothing has no goal to be judged on: its call is done when every judge held. A call still on the
# line is last: nothing of it is known yet.
def is_done(row: ComparisonRow) -> bool:
    """Whether the call did its caller's task: its goal held, or, with no goal judged, every judge did."""
    if row.goal is not None:
        return row.goal == "held"
    return row.score is not None and row.score.passed


# Each caller's rows together, the callers in the order placed, so a table reads one caller at a time.
def ranked(rows: Sequence[ComparisonRow]) -> list[ComparisonRow]:
    """The rows best first, caller by caller."""
    order = {persona: at for at, persona in enumerate(in_the_order_placed(rows))}

    def key(row: ComparisonRow) -> tuple[int, bool, bool, bool, float, float, float]:
        judged = row.score is not None and row.score.judged > 0
        passed = row.score is not None and row.score.passed
        share = row.score.held / row.score.judged if judged and row.score is not None else 0.0
        e2e = row.latency.e2e_latency if row.latency.e2e_latency is not None else float("inf")
        cost = row.cost_usd if row.cost_usd is not None else float("inf")
        return (order[row.persona], row.ended_at is None, not is_done(row), not passed, -share, e2e, cost)

    return sorted(rows, key=key)


# ── a comparison placed in turns ──


@dataclass(frozen=True, slots=True)
class Pair:
    """One call a comparison is to place: the caller, and the agent's values it rings under."""

    persona: str
    against: dict[str, Any]


@dataclass
class Plan:
    """A comparison as it was asked for, and how its placing stands."""

    comparison: str
    agent: str
    scope: Scope
    voice: bool
    personas: list[str]
    against: list[dict[str, Any]]
    repeats: int
    started_at: float
    waiting: int = 0
    refused: list[ComparedRefusal] = field(default_factory=list[ComparedRefusal])
    heard_at: float = 0.0

    @property
    def planned(self) -> int:
        """Every call the comparison was to place."""
        return len(self.personas) * len(self.against) * self.repeats

    def pairs(self) -> list[Pair]:
        """Every call to place, a round of every caller under every setup, then the next round."""
        once = [Pair(persona, values) for persona in self.personas for values in self.against]
        return once * self.repeats

    def document(self) -> dict[str, Any]:
        """The plan as its row keeps it."""
        return {
            "voice": self.voice,
            "personas": self.personas,
            "against": self.against,
            "repeats": self.repeats,
            "waiting": self.waiting,
            "refused": [one.model_dump() for one in self.refused],
            "heard_at": self.heard_at,
        }


async def keep_plan(session: AsyncSession, plan: Plan) -> None:
    """Write the comparison's plan, whole."""
    await ComparisonRepository(session).put(
        id=plan.comparison,
        org=plan.scope.org,
        env=plan.scope.env,
        agent=plan.agent,
        started_at=plan.started_at,
        document=plan.document(),
    )


async def plan_of(session: AsyncSession, scope: Scope, comparison: str) -> Plan | None:
    """The comparison as it was asked for; None for one made before plans were kept, and for nobody's."""
    row = await ComparisonRepository(session).get(scope.org, scope.env, comparison)
    if row is None:
        return None
    kept = row.document
    refused: list[dict[str, Any]] = list(kept.get("refused") or [])
    return Plan(
        comparison=row.id,
        agent=row.agent,
        scope=scope,
        voice=bool(kept.get("voice")),
        personas=list(kept.get("personas") or []),
        against=list(kept.get("against") or []),
        repeats=int(kept.get("repeats") or 1),
        started_at=row.started_at,
        waiting=int(kept.get("waiting") or 0),
        refused=[ComparedRefusal.model_validate(one) for one in refused],
        heard_at=float(kept.get("heard_at") or 0.0),
    )


def was_left(plan: Plan, now: float) -> bool:
    """Whether calls still wait and the gateway placing them stopped saying so: they never will be placed."""
    return plan.waiting > 0 and now - plan.heard_at > LEFT_AFTER_S


# A place on the line is the org's own ceiling, so it is waited for; anything else that refuses a
# call (a vendor nobody keyed, the month's simulations used up) would refuse it again a second later.
type Place = Callable[[Pair], Awaitable[object]]
type Said = Callable[[], Awaitable[None]]


async def place_waiting(
    plan: Plan,
    waiting: Sequence[Pair],
    place: Place,
    said: Said,
    *,
    clock: Callable[[], float],
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    """Place each call that waits as a place on the line frees, saying how the placing stands as it goes."""
    began = clock()
    left = list(waiting)
    while left:
        pair = left[0]
        try:
            await place(pair)
        except TooManyAtOnce:
            waited = clock() - began
            if waited >= PLACING_GIVES_UP_AFTER_S:
                why = NEVER_GOT_A_PLACE.format(minutes=waited / 60)
                plan.refused += [ComparedRefusal(persona=one.persona, against=one.against, why=why) for one in left]
                left = []
            elif clock() - plan.heard_at >= STILL_PLACING_EVERY_S:
                plan.heard_at = clock()
                await said()
            if left:
                await sleep(A_PLACE_IS_ASKED_EVERY_S)
            continue
        except PinecallError as why:
            plan.refused.append(ComparedRefusal(persona=pair.persona, against=pair.against, why=str(why)))
        left.pop(0)
        plan.waiting = len(left)
        plan.heard_at = clock()
        await said()
    plan.waiting = 0
    plan.heard_at = clock()
    await said()
