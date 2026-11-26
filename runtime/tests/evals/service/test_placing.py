"""A comparison's placing: the calls that wait placed as the line frees, and what is left to place after a take-up."""

from dataclasses import dataclass, field
from typing import override

from sqlalchemy.exc import TimeoutError as PoolTimeout

from runtime.actor import Scope
from runtime.enums import Env
from runtime.evals.service.placing import (
    PLACING_GIVES_UP_AFTER_S,
    list_left_to_place,
    place_waiting,
    refusal_for_good,
    refusing_what_stopped,
)
from runtime.evals.service.plans import Pair, Plan, Refused, Stopped
from runtime.evals.tasks import TooManyAtOnce
from runtime.exceptions import ServiceUnavailable
from runtime.postgres import A_CONNECTION_IS_WAITED_FOR_S
from runtime.wire.base import Entry

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


A_FULL_POOL = "QueuePool limit of size 8 overflow 0 reached, connection timed out, timeout 2.00"


@dataclass
class ABusyDatabase(Line):
    """A line whose database has no connection free for the first asks of one caller, or for any of them."""

    busy_for: str = ""
    refusals: int = 0
    asked: int = 0
    breaks: str | None = None

    @override
    async def place(self, pair: Pair) -> None:
        if pair.persona == self.breaks:
            raise KeyError("a fault of the gateway's own")
        if pair.persona == self.busy_for:
            self.asked += 1
            if self.asked <= self.refusals:
                raise PoolTimeout(A_FULL_POOL)
        await super().place(pair)

    async def passes(self, seconds: float) -> None:
        self.now += max(seconds, 1.0)


# 2026-11-25, cmp_bf669d1c4545: twenty calls on a gateway whose pool is eight. The twentieth found no
# connection in two seconds; the comparison then read twenty planned, nineteen rows, none waiting and
# none refused for good, and the command that followed it never returned.
async def test_a_placing_that_finds_no_connection_free_is_asked_again_and_placed() -> None:
    plan = a_plan()
    line = ABusyDatabase(places=10, busy_for="books", refusals=3)
    await place_waiting(plan, plan.list_pairs(), line.place, line.say, clock=line.clock, sleep=line.passes)
    assert line.placed == plan.list_pairs()
    assert (plan.waiting, plan.refused) == (0, [])


async def test_a_placing_the_database_never_has_a_connection_for_is_refused_as_busy_and_the_rest_go_on() -> None:
    plan = a_plan()
    line = ABusyDatabase(places=10, busy_for="books", refusals=10_000)
    await place_waiting(plan, plan.list_pairs(), line.place, line.say, clock=line.clock, sleep=line.passes)
    assert [pair.persona for pair in line.placed] == ["cancels", "cancels"]
    assert [(one.persona, one.against) for one in plan.refused] == [("books", {}), ("books", {"llm": "acme/quick"})]
    assert all("the database was busy: no connection came free in" in one.why for one in plan.refused)
    assert line.now >= 2 * A_CONNECTION_IS_WAITED_FOR_S
    # Every call asked for is a call, a call that waits or a refusal: the count a reader waits on closes.
    assert plan.planned == len(line.placed) + plan.waiting + len(plan.refused)


async def test_a_placing_that_breaks_is_a_refusal_by_the_kind_of_what_broke_and_never_the_end_of_the_placing() -> None:
    plan = a_plan()
    line = ABusyDatabase(places=10, breaks="books")
    await place_waiting(plan, plan.list_pairs(), line.place, line.say, clock=line.clock, sleep=line.passes)
    assert [pair.persona for pair in line.placed] == ["cancels", "cancels"]
    assert [one.why for one in plan.refused] == [
        "the gateway could not place this call (KeyError): its log says why"
    ] * 2
    assert plan.waiting == 0


# ── a setup rung no more ──

NO_CREDIT = "a vendor of the agent failed the call: acme refused this call's model: You have no credits remaining."


# 2026-11-26: a vendor whose account was out of credit was rung for every call still waiting of its
# setup, each one opened, refused and paid for on the caller's side.
async def test_the_calls_of_a_stopped_setup_are_refused_in_its_vendors_words_and_none_is_placed() -> None:
    plan = a_plan()
    plan.stopped.append(Stopped({"llm": "acme/quick"}, NO_CREDIT))
    line = Line(places=4)
    rung = refusing_what_stopped(plan, line.place)
    await place_waiting(plan, plan.list_pairs(), rung, line.say, clock=line.clock)
    assert line.placed == [Pair("books", {}), Pair("cancels", {})]
    assert [(one.persona, one.against) for one in plan.refused] == [
        ("books", {"llm": "acme/quick"}),
        ("cancels", {"llm": "acme/quick"}),
    ]
    assert all(one.why == f"no more calls are placed on this setup: {NO_CREDIT}" for one in plan.refused)
    assert plan.waiting == 0


def an_error(code: str, message: str) -> Entry:
    said = {"code": code, "message": message}
    return Entry(seq=1, ts=1.0, call="call_1", agent="front-desk", type="error", ephemeral=False, data=said)


def test_a_refusal_no_retry_changes_is_told_from_a_vendor_that_failed_and_names_who_cannot_be_paid() -> None:
    no_credit = (
        "openai refused this call's model: You have no credits remaining.\nlabel='livekit.plugins.openai.llm.LLM'"
    )
    assert refusal_for_good([an_error("component_dead_end", no_credit)]) == (True, "openai")
    # A realtime model's refusal for payment is words alone, and its handshake's a status.
    handshake = "xai refused this call: it answered the connection 402 Payment Required"
    assert refusal_for_good([an_error("component_failed", handshake)]) == (True, "xai")
    # A model the vendor does not know stops its setup, and no other of that vendor.
    unknown = "acme refused this call's model: The model does not exist"
    assert refusal_for_good([an_error("component_dead_end", unknown)]) == (True, "")
    assert refusal_for_good([an_error("component_failed", "google failed on its side (504): server error")]) == (
        False,
        "",
    )
    assert refusal_for_good([an_error("never_served", "no worker served the call")]) == (False, "")
