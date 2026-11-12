"""A call's panel: the judges it meets, the gate that settles one before any model is asked, the facts they are told."""

import dataclasses

from runtime.enums import Direction, JudgeAnswer, JudgeRunsWhen
from runtime.judging.service.asking import Context
from runtime.judging.service.judge_model import JudgeModel
from runtime.judging.service.judges import PINECALL, THE_ORG, RosterJudge
from runtime.judging.service.library import library_judges
from runtime.judging.service.panel import (
    Panel,
    Surroundings,
    alone,
    ask_panel,
    evidence_at,
    facts_of,
    gate_of,
    panel_of,
    skip_unjudged,
)
from runtime.judging.service.specs import JudgeSpec
from runtime.judging.service.transcript import Transcript, transcript_of
from runtime.providers.stage import Running
from runtime.wire.base import Entry
from runtime.wire.scores import CallScore
from tests.conftest import configured
from tests.fakes.acme import ACME, MODEL, AcmeLLM
from tests.judging.factories import (
    THE_CLINIC,
    Scripted,
    a_log,
    a_transcript,
    agent,
    agent_line,
    caller,
    caller_line,
    confirmed,
    entry,
)

SLOT = JudgeSpec(name="offers-next-slot", question="Did the agent offer the next free slot?")


REHEARSED = JudgeSpec(name="names-the-doctor", question="Was the doctor named?", when=JudgeRunsWhen.simulations)


def plain() -> Transcript:
    return a_transcript(caller_line("¿Hay hueco?"), agent_line("El viernes a las diez."))


# A roster as the store answers one: Pinecall's judges by name, each as switched, then the org's own.
def a_roster(switched: dict[str, bool], *own: JudgeSpec) -> list[RosterJudge]:
    """Every judge of the library as these switches leave it, and the org's own after them."""
    library = [
        RosterJudge(
            judge.spec,
            owner=PINECALL,
            on=switched.get(name, judge.on_by_default),
            gate=judge.gate,
            version=judge.version,
        )
        for name, judge in sorted(library_judges().items())
    ]
    return [*library, *(RosterJudge(spec, owner=THE_ORG, on=True) for spec in own)]


def names(seated: tuple[RosterJudge, ...]) -> list[str]:
    return [judge.spec.name for judge in seated]


# ── the panel ──


def test_a_call_no_switch_touched_meets_none_of_the_library() -> None:
    assert panel_of(a_roster({}), plain()) == ()


def test_a_real_call_meets_the_library_switched_on_in_name_order_and_no_rehearsal() -> None:
    switched = {"promises": True, "consent": True, "expected-outcome": True}
    assert names(panel_of(a_roster(switched), plain())) == ["consent", "promises"]


def test_a_simulated_call_meets_the_judges_only_simulations_run() -> None:
    simulated = dataclasses.replace(plain(), simulated=True)
    assert "expected-outcome" in names(panel_of(a_roster({"expected-outcome": True}), simulated))
    assert REHEARSED.name in names(panel_of(a_roster({}, REHEARSED), simulated))
    assert REHEARSED.name not in names(panel_of(a_roster({}, REHEARSED), plain()))


def test_a_switch_turns_one_of_pinecalls_on_or_off() -> None:
    seated = names(panel_of(a_roster({"grounded": True, "sentiment": True}), plain()))
    assert seated == ["grounded", "sentiment"]
    assert names(panel_of(a_roster({"grounded": False, "sentiment": True}), plain())) == ["sentiment"]


def test_the_orgs_own_judges_follow_the_library_in_the_order_given() -> None:
    other = JudgeSpec(name="says-the-price", question="Was the price said?")
    seated = panel_of(a_roster({"grounded": True}, SLOT, other), plain())
    assert names(seated)[-2:] == [SLOT.name, other.name]
    assert (seated[-1].gate, seated[-1].version) == ("none", None)
    assert seated[0].version == library_judges()[seated[0].spec.name].version


# ── the gates ──


def library_seat(name: str) -> RosterJudge:
    (judge,) = (one for one in a_roster({name: True}) if one.spec.name == name)
    return judge


def test_consent_is_na_on_a_call_no_irreversible_tool_ran_on() -> None:
    assert gate_of(library_seat("consent"), plain()) == ("no tool this agent declares irreversible ran on this call")
    assert gate_of(library_seat("consent"), transcript_of(confirmed(), THE_CLINIC)) is None


def test_identified_is_na_on_a_call_that_came_in() -> None:
    inbound = dataclasses.replace(plain(), direction=Direction.inbound)
    outbound = dataclasses.replace(plain(), direction=Direction.outbound)
    assert gate_of(library_seat("identified"), inbound) is not None
    assert gate_of(library_seat("identified"), outbound) is None


def test_expected_outcome_is_na_when_the_simulated_caller_expected_nothing() -> None:
    expecting = dataclasses.replace(plain(), expects=("The agent should give a price.",))
    assert gate_of(library_seat("expected-outcome"), plain()) == ("the simulated caller expected nothing of the agent")
    assert gate_of(library_seat("expected-outcome"), expecting) is None


def test_a_judge_with_no_gate_is_always_asked() -> None:
    assert gate_of(RosterJudge(SLOT, owner=THE_ORG, on=True), plain()) is None


# ── the facts ──


def test_the_facts_name_the_org_the_direction_and_the_irreversible_tools_and_gate() -> None:
    lines = facts_of(transcript_of(confirmed(), THE_CLINIC), Surroundings(org="Clínica Norte"))
    assert lines.split("\n") == [
        "- organisation: Clínica Norte",
        "- direction: unknown",
        "- irreversible tools: book_appointment",
        "- #3 confirm.request book_appointment (caller)",
        "- #5 confirm.granted book_appointment (caller)",
        "- an opt-out was written on this call: no",
    ]


def test_the_facts_carry_the_opt_out_the_disclosure_the_ending_and_the_expectations() -> None:
    case = dataclasses.replace(
        plain(),
        direction=Direction.outbound,
        summary={"end_reason": "caller_hung_up", "ended_by": "caller"},
        expects=("The agent should give a price.", "The agent should not promise a call back."),
    )
    around = Surroundings(org="Clínica Norte", disclosure="Le llama un asistente.", opted_out=True)
    lines = facts_of(case, around).split("\n")
    assert lines[1] == "- direction: outbound"
    assert lines[2] == "- irreversible tools: none"
    assert lines[3:] == [
        "- an opt-out was written on this call: yes",
        '- the disclosure sentence outbound calls open with: "Le llama un asistente."',
        "- the call ended: caller_hung_up, by caller",
        "- the simulated caller expected:",
        "  - The agent should give a price.",
        "  - The agent should not promise a call back.",
    ]


# ── at hang-up: the panel asked ──

PRICE = JudgeSpec(name="says-the-price", question="Did the agent say the price?")
MOOD = JudgeSpec(name="mood", question="How did the caller feel?", answer=JudgeAnswer.choice, choices=("good", "bad"))
REFUND = JudgeSpec(
    name="refund-offered",
    question="Did the agent offer the refund?",
    when=JudgeRunsWhen.trigger,
    trigger="The caller asked for a refund.",
)
# One answer of the judge's model: its words, or the tool calls it makes.
type Reply = list[str | dict[str, object]]
# The judge's model on a key of the org's, held to a cent a call: acme's, which the suite's row prices.
THE_JUDGE = Running(ACME, "k", model=MODEL)


def only(*named: str) -> dict[str, bool]:
    """Switches that leave on only the library's judges named."""
    return {name: name in named for name in library_judges()}


def answered(given: str, reason: str = "because", positions: list[int] | None = None) -> Reply:
    """One scripted reply: the judge's verdict, its reason and the positions it rests on."""
    seqs: list[object] = list(positions or [])
    return [{"name": "submit_verdict", "arguments": {"verdict": given, "reason": reason, "positions": seqs}}]


def a_call() -> list[Entry]:
    return a_log(caller("¿Cuánto cuesta?"), agent("Son 45 euros."))


def a_panel(switched: dict[str, bool], *own: JudgeSpec) -> Panel:
    """The panel a call of the clinic meets, as the store's roster and these switches leave it."""
    transcript = transcript_of(a_call(), THE_CLINIC)
    return Panel(transcript, panel_of(a_roster(switched, *own), transcript), Context(), configured())


async def judged(panel: Panel, replies: list[Reply], judge: JudgeModel | None = None) -> CallScore:
    """The call's score: its panel asked of a model that answers these replies in order."""
    asked = Scripted(AcmeLLM(api_key="k", replies=replies))
    return (await ask_panel(panel, judge or JudgeModel(THE_JUDGE, 0.01), a_call(), asked)).score


def verdicts_of(score: CallScore) -> dict[str, str]:
    return {judgment.name: judgment.verdict for judgment in score.judges}


async def test_a_held_verdict_passes_the_call_and_is_one_eval_counted_and_priced() -> None:
    score = await judged(a_panel(only("grounded")), [answered("held", "the price was in the tool's answer")])
    assert verdicts_of(score) == {"grounded": "held"}
    assert (score.passed, score.evals, score.judge_calls) == (True, 1, 1)
    assert score.panel == ["grounded"]
    assert score.judge_cost_usd is not None and score.judge_cost_usd > 0
    assert score.judged_by is not None
    assert (score.judged_by.provider, score.judged_by.model) == (ACME, MODEL)


async def test_the_same_questions_hash_the_same_whatever_the_call_said() -> None:
    first = await judged(a_panel(only("grounded")), [answered("held")])
    second = await judged(a_panel(only("grounded")), [answered("broken")])
    assert first.judged_by == second.judged_by


async def test_a_broken_verdict_fails_the_call_and_carries_the_lines_it_rests_on() -> None:
    score = await judged(a_panel(only("grounded")), [answered("broken", "45 is nowhere", positions=[2, 9])])
    [judgment] = score.judges
    assert (judgment.verdict, judgment.reason, score.passed) == ("broken", "45 is nowhere", False)
    assert judgment.evidence.seqs == [2]
    assert judgment.evidence.said == "Son 45 euros."
    assert judgment.criteria == library_judges()["grounded"].spec.question


async def test_a_gate_settles_na_before_any_model_is_asked_and_bills_nothing() -> None:
    score = await judged(a_panel(only("consent")), [])
    [judgment] = score.judges
    assert (judgment.verdict, judgment.reason) == ("na", "no tool this agent declares irreversible ran on this call")
    assert (score.passed, score.not_judged, score.evals, score.judge_calls) == (None, None, 0, 0)


def test_with_no_model_every_judge_is_skipped_saying_why() -> None:
    score = skip_unjudged(a_panel(only("grounded")), a_call(), "no judge here").score
    assert verdicts_of(score) == {"grounded": "skipped"}
    assert (score.passed, score.not_judged, score.judge_calls) == (None, "no judge here", 0)
    assert score.judged_by is not None
    assert (score.judged_by.provider, score.judged_by.model) == (None, None)


async def test_a_judge_whose_model_failed_is_skipped_and_the_call_still_scored() -> None:
    score = await judged(a_panel(only("grounded")), [["nada"]])
    [judgment] = score.judges
    assert judgment.verdict == "skipped"
    assert "the judge model failed" in judgment.reason
    assert score.not_judged == "every judge run over this call failed and not one of them answered"


# A panel with nobody on it was said as "every judge run failed" (2026-10-17, a new org on a laptop,
# where no judge is on until somebody switches one): the sentence names the verb instead.
async def test_a_call_with_no_judge_on_says_so_and_names_the_verb() -> None:
    score = await judged(a_panel(only()), [])
    assert score.judges == [] and score.judge_calls == 0
    assert score.not_judged is not None and score.not_judged.startswith("no judge is on for this agent")
    assert "`pinecall judges on <name>`" in score.not_judged


async def test_a_judge_asked_past_the_ceiling_is_skipped_and_the_ones_before_it_stand() -> None:
    tight = JudgeModel(THE_JUDGE, 0.000001)
    score = await judged(a_panel(only(), SLOT, PRICE), [answered("held")] * 2, tight)
    assert verdicts_of(score) == {SLOT.name: "held", PRICE.name: "skipped"}
    assert score.judges[1].reason.startswith("judging this call reached its ceiling of $1e-06")
    assert (score.judge_calls, score.evals, score.passed) == (1, 1, True)


async def test_once_the_orgs_evals_are_used_up_the_judges_after_are_not_asked() -> None:
    replies = [answered("held")] * 2
    one_left = JudgeModel(THE_JUDGE, 0.01, evals_left=1)
    score = await judged(a_panel(only(), SLOT, PRICE), replies, one_left)
    assert verdicts_of(score) == {SLOT.name: "held", PRICE.name: "skipped"}
    assert score.judges[1].reason.startswith("the org's evals for the month are used up")
    none_left = JudgeModel(THE_JUDGE, 0.01, evals_left=0)
    asked = Scripted(AcmeLLM(api_key="k", replies=replies))
    nothing = await ask_panel(a_panel(only(), SLOT), none_left, a_call(), asked)
    assert (verdicts_of(nothing.score), nothing.score.judge_calls, nothing.out_of_evals) == (
        {SLOT.name: "skipped"},
        0,
        True,
    )


async def test_a_classification_is_an_eval_and_never_passes_or_fails_the_call() -> None:
    chosen: list[Reply] = [[{"name": "submit_choice", "arguments": {"choice": "bad", "reason": "r"}}]]
    score = await judged(a_panel(only(), MOOD), chosen)
    [judgment] = score.judges
    assert (judgment.verdict, judgment.choice) == ("classified", "bad")
    assert (score.passed, score.not_judged, score.evals) == (None, None, 1)


async def test_a_trigger_that_did_not_hold_is_na_its_request_counted_and_no_eval() -> None:
    applies: list[Reply] = [[{"name": "submit_applies", "arguments": {"applies": False, "reason": "no refund"}}]]
    score = await judged(a_panel(only(), REFUND), applies)
    assert verdicts_of(score) == {REFUND.name: "na"}
    assert (score.judge_calls, score.evals) == (1, 0)


async def test_the_library_switched_on_comes_first_then_the_orgs_own() -> None:
    score = await judged(a_panel(only("grounded"), SLOT, REHEARSED), [answered("held")] * 3)
    assert score.panel == ["grounded", SLOT.name], "a judge for simulations meets no real call"


# ── one judge alone ──


def test_one_of_the_librarys_alone_is_asked_as_pinecalls_with_its_gate() -> None:
    consent = library_judges()["consent"]
    (judge,) = alone(consent.spec)
    assert (judge.owner, judge.on, judge.gate, judge.version) == (PINECALL, True, consent.gate, consent.version)


def test_a_judge_of_ones_own_alone_is_the_orgs() -> None:
    (judge,) = alone(PRICE)
    assert (judge.spec, judge.owner, judge.on, judge.gate) == (PRICE, THE_ORG, True, "none")


def test_a_question_rewritten_under_a_librarys_name_is_asked_as_written() -> None:
    rewritten = dataclasses.replace(library_judges()["consent"].spec, question="Did the caller agree?")
    (judge,) = alone(rewritten)
    assert (judge.spec, judge.owner, judge.gate) == (rewritten, THE_ORG, "none")


# ── the lines an answer rests on ──


def test_the_positions_an_answer_names_become_the_entries_a_reader_opens() -> None:
    log = [entry(4, "tool.call", {}), entry(6, "turn.agent", {"text": "Hecho."})]
    evidence = evidence_at([9, 4, 6], log)
    assert (evidence.seqs, evidence.said) == ([4, 6], "Hecho.")


def test_an_answer_that_names_no_line_carries_no_evidence_and_no_words() -> None:
    evidence = evidence_at([], a_call())
    assert (evidence.seqs, evidence.said) == ([], None)
