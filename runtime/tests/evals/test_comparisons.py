"""A comparison's rows: a call's latency medians read off its log, and the rows ranked best first."""

from dataclasses import dataclass, field
from pathlib import Path

from pydantic import TypeAdapter

from pinecall_runtime.enums import Env
from pinecall_runtime.evals.schemas import ComparedRefusal, ComparisonRow, Latency, RowVerdict, SessionScore
from pinecall_runtime.evals.service.comparisons import (
    LEFT_AFTER_S,
    PLACING_GIVES_UP_AFTER_S,
    Pair,
    Plan,
    goal_of,
    in_the_order_placed,
    is_done,
    latency_of,
    place_waiting,
    ranked,
    verdicts_of,
    was_left,
    why_it_never_began,
)
from pinecall_runtime.evals.service.simulations import TooManyAtOnce
from pinecall_runtime.exceptions import ServiceUnavailable
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.kit.text import Json, JsonObject
from pinecall_runtime.wire.base import Entry
from pinecall_runtime.wire.parts import ScoreVerdict

ACME = Scope("org_acme", Env.sandbox)
GOLDEN = Path(__file__).resolve().parents[1] / "wire" / "golden" / "call-log.json"
_ENTRIES: TypeAdapter[list[Entry]] = TypeAdapter(list[Entry])


def test_a_calls_latency_is_each_measures_median_over_its_turns() -> None:
    """The golden log's turns carry their metrics: the medians are numbers, and a measure no turn took is None."""
    entries = _ENTRIES.validate_json(GOLDEN.read_bytes())
    latency = latency_of(entries)
    assert latency.e2e_latency is not None and latency.e2e_latency > 0
    assert latency.llm_node_ttft is not None and latency.llm_node_ttft > 0
    assert latency_of([]) == Latency(
        e2e_latency=None, llm_node_ttft=None, tts_node_ttfb=None, transcription_delay=None, end_of_turn_delay=None
    )


def a_row(
    call: str,
    *,
    ended: bool = True,
    score: SessionScore | None = None,
    e2e: float | None = None,
    cost: float | None = None,
    persona: str = "in-a-hurry",
    started_at: float = 1.0,
    goal: ScoreVerdict | None = None,
) -> ComparisonRow:
    """One call of a comparison as its row."""
    return ComparisonRow(
        call=call,
        persona=persona,
        against={"llm": f"acme/{call}"},
        started_at=started_at,
        ended_at=40.0 if ended else None,
        turns=4,
        end_reason="caller_hung_up" if ended else None,
        score=score,
        cost_usd=cost,
        latency=Latency(
            e2e_latency=e2e, llm_node_ttft=None, tts_node_ttfb=None, transcription_delay=None, end_of_turn_delay=None
        ),
        why=None,
        goal=goal,
    )


def test_the_rows_are_ranked_by_judges_then_speed_then_cost_with_a_live_call_last() -> None:
    """Every judge held beats most held; then the fastest reply; then the cheapest; a call still on the line is last."""
    held = SessionScore(held=4, judged=4, passed=True, reason=None)
    mostly = SessionScore(held=3, judged=4, passed=False, reason="one broke")
    rows = [
        a_row("live", ended=False),
        a_row("cheap-but-broke", score=mostly, e2e=0.8, cost=0.01),
        a_row("held-slow", score=held, e2e=2.0, cost=0.02),
        a_row("held-fast-dear", score=held, e2e=1.0, cost=0.05),
        a_row("held-fast-cheap", score=held, e2e=1.0, cost=0.02),
        a_row("unjudged", score=None, e2e=0.5, cost=0.01),
    ]
    assert [row.call for row in ranked(rows)] == [
        "held-fast-cheap",
        "held-fast-dear",
        "held-slow",
        "cheap-but-broke",
        "unjudged",
        "live",
    ]


def test_several_callers_are_ranked_each_on_its_own_in_the_order_they_were_placed() -> None:
    """A table of two callers reads one caller at a time: the first placed, its best first, then the next."""
    held = SessionScore(held=2, judged=2, passed=True, reason=None)
    rows = [
        a_row("rude-fast", persona="angry", started_at=2.0, score=held, e2e=0.5),
        a_row("hurry-slow", persona="in-a-hurry", started_at=1.0, score=held, e2e=2.0),
        a_row("rude-slow", persona="angry", started_at=2.1, score=held, e2e=3.0),
        a_row("hurry-fast", persona="in-a-hurry", started_at=1.1, score=held, e2e=1.0),
    ]
    assert in_the_order_placed(rows) == ["in-a-hurry", "angry"]
    assert [row.call for row in ranked(rows)] == ["hurry-fast", "hurry-slow", "rude-fast", "rude-slow"]


def test_why_a_call_never_began_is_its_unrecoverable_error_and_nothing_for_one_that_ran() -> None:
    """The worker's refusal before call.started names why; a call that started has no why, whatever errors it met."""
    entries = _ENTRIES.validate_json(GOLDEN.read_bytes())
    assert why_it_never_began(entries) is None
    refused = Entry(
        seq=2,
        ts=2.0,
        call="call_1",
        agent="a",
        type="error",
        ephemeral=False,
        data={"code": "session_failed", "message": "soniox refused its STT", "recoverable": False},
    )
    assert why_it_never_began([refused]) == "soniox refused its STT"


def a_score(seq: int, *judges: tuple[str, str]) -> Entry:
    """A call's score entry: each judge by its name and verdict."""
    answered: list[Json] = [
        {"name": name, "verdict": verdict, "criteria": "", "reason": f"{name} {verdict}", "evidence": {"seqs": []}}
        for name, verdict in judges
    ]
    data: JsonObject = {"passed": True, "judges": answered, "judge_calls": len(judges)}
    return Entry(seq=seq, ts=float(seq), call="call_1", agent="a", type="call.score", ephemeral=False, data=data)


def test_a_rows_verdicts_are_the_judges_that_answered_and_none_before_the_score() -> None:
    """A judge deferred or skipped said nothing of the call; a call not scored yet has no verdict at all."""
    assert verdicts_of([]) == []
    scored = a_score(9, ("expected-outcome", "broken"), ("promises", "held"), ("tone", "skipped"))
    assert verdicts_of([scored]) == [
        RowVerdict(name="expected-outcome", verdict="broken", reason="expected-outcome broken"),
        RowVerdict(name="promises", verdict="held", reason="promises held"),
    ]


def test_the_goal_is_the_verdict_of_the_judge_of_what_the_caller_expected() -> None:
    """The task is that one judge's: another judge holding says nothing of it, and without it there is no goal."""
    assert goal_of(verdicts_of([a_score(9, ("promises", "held"), ("expected-outcome", "held"))])) == "held"
    assert goal_of(verdicts_of([a_score(9, ("promises", "held"))])) is None


# The fault: a call that booked the appointment and broke the language judge ranked under one that
# booked nothing and broke nothing else, because a row knew only whether every judge had held.
def test_a_call_that_did_its_task_ranks_over_one_that_held_more_judges_and_did_not() -> None:
    """The caller's goal comes first; with no goal judged, a call is done when every judge held."""
    mostly = SessionScore(held=3, judged=4, passed=False, reason="one broke")
    held = SessionScore(held=4, judged=4, passed=True, reason=None)
    rows = [
        a_row("polite-no-booking", score=mostly, goal="broken", e2e=0.5),
        a_row("booked-wrong-language", score=mostly, goal="held", e2e=2.0),
        a_row("booked-clean", score=held, goal="held", e2e=3.0),
    ]
    assert [row.call for row in ranked(rows)] == ["booked-clean", "booked-wrong-language", "polite-no-booking"]
    assert is_done(a_row("no-goal-held", score=held)) is True
    assert is_done(a_row("no-goal-broke", score=mostly)) is False
    assert is_done(a_row("goal-na", score=held, goal="na")) is False


# ── a comparison placed in turns ──


def a_plan(*, repeats: int = 1, waiting: int = 0, heard_at: float = 0.0) -> Plan:
    """A comparison of two callers under two setups, each once, unless said."""
    return Plan(
        comparison="cmp_1",
        agent="front-desk",
        scope=ACME,
        voice=True,
        personas=["books", "cancels"],
        against=[{}, {"llm": "acme/quick"}],
        repeats=repeats,
        started_at=0.0,
        waiting=waiting,
        heard_at=heard_at,
    )


@dataclass
class Line:
    """An org's line with so many places: a call placed takes one, and `ends` gives places back."""

    places: int
    placed: list[Pair] = field(default_factory=list[Pair])
    now: float = 0.0
    said: int = 0
    unkeyed: str | None = None

    async def place(self, pair: Pair) -> None:
        if pair.persona == self.unkeyed:
            raise ServiceUnavailable("nobody keyed the caller's vendor")
        if self.places == 0:
            raise TooManyAtOnce(Env.sandbox, len(self.placed))
        self.places -= 1
        self.placed.append(pair)

    async def say(self) -> None:
        self.said += 1

    def clock(self) -> float:
        return self.now


def test_a_comparison_plans_a_round_of_every_caller_under_every_setup_then_the_next_round() -> None:
    """Repeats are rounds, so a comparison cut short has every cell once before any has it twice."""
    plan = a_plan(repeats=2)
    assert plan.planned == 8
    pairs = plan.pairs()
    assert pairs[:4] == pairs[4:]
    assert [(pair.persona, pair.against) for pair in pairs[:4]] == [
        ("books", {}),
        ("books", {"llm": "acme/quick"}),
        ("cancels", {}),
        ("cancels", {"llm": "acme/quick"}),
    ]


# The fault this is for: a comparison placed every call at once, so one larger than the org's
# ceiling had its last calls refused and never placed.
async def test_the_calls_that_wait_are_placed_as_places_on_the_line_free() -> None:
    """A call with no place waits and asks again; each one placed is said, and none is left waiting."""
    plan = a_plan(repeats=2)
    waiting = plan.pairs()[2:]
    plan.waiting = len(waiting)
    line = Line(places=1)

    async def a_call_ends(_: float) -> None:
        line.now += 2.0
        line.places += 1

    await place_waiting(plan, waiting, line.place, line.say, clock=line.clock, sleep=a_call_ends)
    assert line.placed == waiting
    assert (plan.waiting, plan.refused) == (0, [])
    assert line.said >= len(waiting)


async def test_a_call_refused_for_another_reason_is_said_and_the_ones_behind_it_go_on() -> None:
    """Only a place on the line is waited for: a vendor nobody keyed refuses that call once, in its words."""
    plan = a_plan()
    line = Line(places=10, unkeyed="books")
    await place_waiting(plan, plan.pairs(), line.place, line.say, clock=line.clock)
    assert [pair.persona for pair in line.placed] == ["cancels", "cancels"]
    assert [(one.persona, one.why) for one in plan.refused] == [("books", "nobody keyed the caller's vendor")] * 2
    assert plan.waiting == 0


async def test_a_line_that_never_frees_is_given_up_on_and_every_call_left_says_why() -> None:
    """Past the longest a comparison waits, what is left is refused rather than asked for forever."""
    plan = a_plan()
    line = Line(places=0)

    async def nothing_ends(_: float) -> None:
        line.now += PLACING_GIVES_UP_AFTER_S / 3

    await place_waiting(plan, plan.pairs(), line.place, line.say, clock=line.clock, sleep=nothing_ends)
    assert line.placed == []
    assert len(plan.refused) == plan.planned
    assert "no place on the line" in plan.refused[0].why
    assert plan.waiting == 0


def test_a_comparison_whose_gateway_stopped_saying_it_places_was_left() -> None:
    """Calls that wait with nobody placing them never will be: the board says so instead of waiting."""
    plan = a_plan(waiting=3, heard_at=100.0)
    assert was_left(plan, 100.0 + LEFT_AFTER_S - 1) is False
    assert was_left(plan, 100.0 + LEFT_AFTER_S + 1) is True
    assert was_left(a_plan(waiting=0, heard_at=100.0), 10_000.0) is False


def test_a_plan_is_kept_as_what_was_asked_and_how_its_placing_stands() -> None:
    """The row's document names the callers, the setups, the repeats, what waits and what was refused."""
    plan = a_plan(repeats=3, waiting=4, heard_at=7.0)
    plan.refused.append(ComparedRefusal(persona="books", against={}, why="the org has used 10 of its 10 simulations"))
    kept = plan.document()
    assert (kept["personas"], kept["against"], kept["repeats"]) == (plan.personas, plan.against, 3)
    assert (kept["waiting"], kept["heard_at"]) == (4, 7.0)
    assert kept["refused"] == [{"persona": "books", "against": {}, "why": "the org has used 10 of its 10 simulations"}]
