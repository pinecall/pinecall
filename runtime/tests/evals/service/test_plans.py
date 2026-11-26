"""A comparison's plan: its rounds, what its row keeps, and when it reads as left."""

from runtime.actor import Actor, Scope
from runtime.enums import Env, KeyScope
from runtime.evals.models import Comparison
from runtime.evals.service.plans import (
    LEFT_AFTER_S,
    PLACED_AGAIN_AT_MOST,
    Judged,
    Pair,
    Plan,
    Refused,
    Stopped,
    Uncounted,
    actor_of,
    is_left,
    is_played,
    names_vendor,
    read_plan,
    say_who_asked,
    settle_uncounted,
    stop_refused,
)
from runtime.evals.service.validity import VALID, Fault, Invalid, Validity

ACME = Scope("org_acme", Env.sandbox)


def kept_as_a_row(plan: Plan) -> Comparison:
    """The plan as its comparison's row keeps it."""
    return Comparison(
        id=plan.comparison, org=ACME.org, env=ACME.env, agent=plan.agent, started_at=0.0, document=plan.dump()
    )


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


def test_a_comparison_plans_a_round_of_every_caller_under_every_setup_then_the_next_round() -> None:
    """Repeats are rounds, so a comparison cut short has every cell once before any has it twice."""
    plan = a_plan(repeats=2)
    assert plan.planned == 8
    pairs = plan.list_pairs()
    assert pairs[:4] == pairs[4:]
    assert [(pair.persona, pair.against) for pair in pairs[:4]] == [
        ("books", {}),
        ("books", {"llm": "acme/quick"}),
        ("cancels", {}),
        ("cancels", {"llm": "acme/quick"}),
    ]


def test_a_comparison_whose_gateway_stopped_saying_it_places_was_left() -> None:
    """Calls that wait with nobody placing them never will be: the board says so instead of waiting."""
    plan = a_plan(waiting=3, heard_at=100.0)
    assert is_left(plan, 100.0 + LEFT_AFTER_S - 1) is False
    assert is_left(plan, 100.0 + LEFT_AFTER_S + 1) is True
    assert is_left(a_plan(waiting=0, heard_at=100.0), 10_000.0) is False


def test_a_plan_is_kept_as_what_was_asked_and_how_its_placing_stands() -> None:
    """The row's document names the callers, the setups, the repeats, what waits and what was refused."""
    plan = a_plan(repeats=3, waiting=4, heard_at=7.0)
    plan.refused.append(Refused(persona="books", against={}, why="the org has used 10 of its 10 simulations"))
    kept = plan.dump()
    assert (kept["personas"], kept["against"], kept["repeats"]) == (plan.personas, plan.against, 3)
    assert (kept["waiting"], kept["heard_at"]) == (4, 7.0)
    assert kept["refused"] == [{"persona": "books", "against": {}, "why": "the org has used 10 of its 10 simulations"}]


# 2026-11-24: a release ended a comparison's gateway, and nothing in its row said how its calls were
# placed or for whom, so nobody could go on with it.
def test_a_plan_keeps_what_another_gateway_places_its_calls_with_and_reads_it_back() -> None:
    asked = Actor(key_id="k_1", org=ACME.org, env=ACME.env, scopes=frozenset({KeyScope.app}), holder="p_ana")
    plan = a_plan(repeats=2)
    plan.wanted, plan.by, plan.done = {"spoken": True, "turns": 6}, say_who_asked(asked), False
    plan.briefs = {"books": {"goal": "a cleaning on Thursday", "facts": {"name": "Maya"}}, "cancels": None}
    plan.replaced = ["call_lost"]
    row = kept_as_a_row(plan)
    read = read_plan(row, Scope(ACME.org, ACME.env, "p_ana"))
    assert (read.wanted, read.briefs, read.replaced, read.done) == (plan.wanted, plan.briefs, ["call_lost"], False)
    again = actor_of(read)
    assert (again.key_id, again.org, again.env, again.scopes, again.holder) == (
        "k_1",
        ACME.org,
        ACME.env,
        asked.scopes,
        "p_ana",
    )
    assert again.person is None


def test_a_plan_made_before_plans_could_be_taken_up_says_nothing_of_it() -> None:
    old = a_plan()
    assert "done" not in old.dump()
    row = kept_as_a_row(old)
    assert read_plan(row, ACME).done is None


# ── a call that did not count ──

QUICK = {"llm": "acme/quick"}
NO_CREDIT = "a vendor of the agent failed the call: acme refused this call's model: You have no credits remaining."


def not_counted(call: str, pair: Pair, kind: Fault, why: str, *, for_good: bool = False, unpaid: str = "") -> Judged:
    """A call of the comparison that ended and did not count, as the placing judges it."""
    return Judged(call, pair, Validity(Invalid(kind, why)), for_good=for_good, unpaid=unpaid)


# 2026-11-26, cmp_cd80e04794c7: 140 calls planned, 19 that did not count (a vendor's 504, two callers'
# own voices, a vendor out of credit), and a table that ended short of them.
def test_a_call_that_did_not_count_is_placed_again_whoever_broke_it_and_stays_settled() -> None:
    plan = a_plan()
    ended = [
        not_counted("call_1", Pair("books", {}), "caller", "the simulated caller's voice broke up"),
        not_counted("call_2", Pair("cancels", {}), "platform", "no worker served the call"),
        not_counted("call_3", Pair("books", QUICK), "vendor", "acme failed on its side (504): server error"),
        Judged("call_4", Pair("cancels", QUICK), VALID),
    ]
    again = settle_uncounted(plan, ended, room=10, most=20)
    assert again == [Pair("books", {}), Pair("cancels", {}), Pair("books", QUICK)]
    assert [(one.call, one.placed_again) for one in plan.uncounted] == [
        ("call_1", True),
        ("call_2", True),
        ("call_3", True),
    ]
    assert (plan.refused, plan.stopped) == ([], [])
    # Read again, as the next pass reads the same calls: each is settled once.
    assert settle_uncounted(plan, ended, room=10, most=20) == []
    assert len(plan.uncounted) == 3


def test_a_place_that_never_counts_is_placed_again_twice_for_each_call_planned_then_refused_saying_why() -> None:
    plan = a_plan(repeats=2)
    books = Pair("books", {})
    placed = 0
    for at in range(PLACED_AGAIN_AT_MOST * 2):
        broke = not_counted(f"call_{at}", books, "caller", "the simulated caller broke on the line")
        placed += len(settle_uncounted(plan, [broke], room=10, most=20))
    assert (placed, plan.refused) == (PLACED_AGAIN_AT_MOST * 2, [])
    once_more = not_counted("call_last", books, "caller", "the simulated caller broke on the line")
    assert settle_uncounted(plan, [once_more], room=10, most=20) == []
    (refused,) = plan.refused
    assert (refused.persona, refused.against) == ("books", {})
    assert refused.why == (
        "no call of this caller on this setup counted, 4 placed again among them: "
        "the simulated caller broke on the line"
    )
    assert plan.uncounted[-1] == Uncounted("call_last", books, placed_again=False)


def test_a_comparison_that_placed_all_its_org_lets_one_place_places_none_for_a_call_that_did_not_count() -> None:
    plan = a_plan()
    ended = [
        not_counted("call_1", Pair("books", {}), "platform", "no worker served the call"),
        not_counted("call_2", Pair("cancels", {}), "platform", "no worker served the call"),
    ]
    assert settle_uncounted(plan, ended, room=1, most=4) == [Pair("books", {})]
    (refused,) = plan.refused
    assert refused.persona == "cancels"
    assert refused.why.startswith("a comparison of this org places 4 calls at most and this one has")


# 2026-11-26: xAI answered 402 to fourteen calls of one comparison, one after another, and OpenAI "no
# credits remaining" to every call of two setups: each was rung to the last call planned.
def test_a_vendor_that_refused_for_good_stops_its_setup_and_its_place_is_refused_in_the_vendors_words() -> None:
    plan = a_plan()
    refused_for_good = not_counted("call_1", Pair("books", QUICK), "vendor", NO_CREDIT, for_good=True)
    assert settle_uncounted(plan, [refused_for_good], room=10, most=20) == []
    assert plan.stopped == [Stopped(QUICK, NO_CREDIT)]
    assert plan.find_stop(QUICK) is not None and plan.find_stop({}) is None
    (refused,) = plan.refused
    assert refused.why == f"no more calls are placed on this setup: {NO_CREDIT}"
    # A call of the same setup that was on the line and ends refused too: its place is refused alike.
    later = not_counted("call_2", Pair("cancels", QUICK), "vendor", NO_CREDIT, for_good=True)
    assert settle_uncounted(plan, [later], room=10, most=20) == []
    assert [one.persona for one in plan.refused] == ["books", "cancels"]
    assert len(plan.stopped) == 1


def test_an_account_that_cannot_pay_stops_every_setup_that_names_its_vendor_and_no_other() -> None:
    plan = a_plan()
    plan.against = [{"llm": "acme/quick"}, {"realtime": "acme/talks"}, {"llm": "other/model"}, {"tts": "acme"}]
    unpaid = not_counted("call_1", Pair("books", {"llm": "acme/quick"}), "vendor", NO_CREDIT, for_good=True)
    stopped = stop_refused(plan, [replace_unpaid(unpaid, "acme")])
    assert [one.against for one in stopped] == [{"llm": "acme/quick"}, {"realtime": "acme/talks"}, {"tts": "acme"}]
    assert plan.find_stop({"llm": "other/model"}) is None
    # A key or a model the vendor does not know is that setup's alone.
    other = a_plan()
    other.against = [{"llm": "acme/quick"}, {"llm": "acme/slow"}]
    unknown = not_counted("call_1", Pair("books", {"llm": "acme/quick"}), "vendor", "acme refused", for_good=True)
    assert [one.against for one in stop_refused(other, [unknown])] == [{"llm": "acme/quick"}]


def replace_unpaid(judged: Judged, vendor: str) -> Judged:
    return Judged(judged.call, judged.pair, judged.validity, for_good=judged.for_good, unpaid=vendor)


def test_a_setup_names_a_vendor_by_itself_or_before_a_model_in_any_stage() -> None:
    assert names_vendor({"llm": "openai/gpt-5.4-mini"}, "openai")
    assert names_vendor({"tts": "cartesia"}, "cartesia")
    assert not names_vendor({"llm": "openai-compatible/x", "voice": "openai"}, "openai")
    assert not names_vendor({}, "openai")


def test_a_plan_keeps_the_calls_that_did_not_count_and_the_setups_stopped_and_reads_them_back() -> None:
    plan = a_plan()
    plan.done = False
    plan.uncounted = [Uncounted("call_1", Pair("books", QUICK), placed_again=True)]
    plan.stopped = [Stopped(QUICK, NO_CREDIT)]
    read = read_plan(kept_as_a_row(plan), ACME)
    assert (read.uncounted, read.stopped) == (plan.uncounted, plan.stopped)


def test_a_comparison_is_played_until_its_last_call_ended_and_while_a_gateway_says_so() -> None:
    plan = a_plan(heard_at=100.0)
    plan.done = False
    assert is_played(plan, 100.0 + LEFT_AFTER_S)
    assert not is_played(plan, 100.0 + LEFT_AFTER_S + 1)
    plan.done = True
    assert not is_played(plan, 100.0)
    old = a_plan(heard_at=100.0)
    assert not is_played(old, 100.0)
