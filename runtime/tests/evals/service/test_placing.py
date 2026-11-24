"""A comparison's placing: the calls that wait placed as the line frees, and what is left to place after a take-up."""

from dataclasses import dataclass, field

from runtime.actor import Scope
from runtime.enums import Env
from runtime.evals.service.placing import PLACING_GIVES_UP_AFTER_S, list_left_to_place, place_waiting
from runtime.evals.service.plans import Pair, Plan, Refused
from runtime.evals.tasks import TooManyAtOnce
from runtime.exceptions import ServiceUnavailable

ACME = Scope("org_acme", Env.sandbox)


def a_plan(*, repeats: int = 1, waiting: int = 0, heard_at: float = 0.0) -> Plan:
    """A comparison of two callers under two setups, each once, unless said."""
    return Plan(
        comparison="cmp_1",
        agent="front-desk",
        scope=ACME,
        spoken=True,
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


# The fault this is for: a comparison placed every call at once, so one larger than the org's
# ceiling had its last calls refused and never placed.
async def test_the_calls_that_wait_are_placed_as_places_on_the_line_free() -> None:
    """A call with no place waits and asks again; each one placed is said, and none is left waiting."""
    plan = a_plan(repeats=2)
    waiting = plan.list_pairs()[2:]
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
    await place_waiting(plan, plan.list_pairs(), line.place, line.say, clock=line.clock)
    assert [pair.persona for pair in line.placed] == ["cancels", "cancels"]
    assert [(one.persona, one.why) for one in plan.refused] == [("books", "nobody keyed the caller's vendor")] * 2
    assert plan.waiting == 0


async def test_a_line_that_never_frees_is_given_up_on_and_every_call_left_says_why() -> None:
    """Past the longest a comparison waits, what is left is refused rather than asked for forever."""
    plan = a_plan()
    line = Line(places=0)

    async def nothing_ends(_: float) -> None:
        line.now += PLACING_GIVES_UP_AFTER_S / 3

    await place_waiting(plan, plan.list_pairs(), line.place, line.say, clock=line.clock, sleep=nothing_ends)
    assert line.placed == []
    assert len(plan.refused) == plan.planned
    assert "no place on the line" in plan.refused[0].why
    assert plan.waiting == 0


# 2026-11-24, on the tests' server: a release fifty seconds into a comparison of twenty-one calls. Eight
# had ended, four were cut with the gateway that played their callers, nine never began; none of the
# thirteen was placed again, and the command that followed the comparison never returned.
def test_what_is_left_to_place_is_every_planned_call_no_call_played_or_refused_stands_for() -> None:
    plan = a_plan(repeats=2)
    quick = {"llm": "acme/quick"}
    played = [Pair("books", {}), Pair("books", quick), Pair("books", {})]
    plan.refused.append(Refused("cancels", quick, "nobody keyed the caller's vendor"))
    assert list_left_to_place(plan, played) == [
        Pair("cancels", {}),
        Pair("books", quick),
        Pair("cancels", {}),
        Pair("cancels", quick),
    ]


def test_a_comparison_whose_every_call_was_played_has_nothing_left_to_place() -> None:
    plan = a_plan()
    assert list_left_to_place(plan, plan.list_pairs()) == []
