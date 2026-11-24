"""A comparison's plan: its rounds, what its row keeps, and when it reads as left."""

from runtime.actor import Actor, Scope
from runtime.enums import Env, KeyScope
from runtime.evals.models import Comparison
from runtime.evals.service.plans import LEFT_AFTER_S, Plan, Refused, actor_of, is_left, read_plan, say_who_asked

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
