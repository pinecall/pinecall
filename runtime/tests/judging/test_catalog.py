"""Tests for the library of judges: every page parses, the panel, the gates, the facts."""

import dataclasses
from collections.abc import Iterator
from pathlib import Path

import pytest

import pinecall_runtime.judging.service.catalog as catalog
from pinecall_runtime.enums import Direction, JudgeRunsWhen
from pinecall_runtime.exceptions import ValidationError
from pinecall_runtime.judging.service.case import Case, case_of
from pinecall_runtime.judging.service.catalog import (
    PERSONAS,
    Seated,
    Surroundings,
    facts_of,
    gated,
    library_judges,
    library_personas,
    panel_of,
)
from pinecall_runtime.judging.service.specs import A_NAME, JudgeSpec
from tests.judging.factories import THE_CLINIC, agent_line, caller_line, case_of_turns, confirmed

SLOT = JudgeSpec(name="offers-next-slot", question="Did the agent offer the next free slot?")


REHEARSED = JudgeSpec(name="names-the-doctor", question="Was the doctor named?", on=JudgeRunsWhen.simulations)


A_PAGE = """---
name: polite
summary: The agent was polite.
answer: verdict
on: always
reads: facts, prompt
gate: none
default: off
version: 3
---

Was the agent polite throughout?
"""


@pytest.fixture
def written_library(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """A library read from a folder of the test's, forgotten again after it."""
    monkeypatch.setattr(catalog, "JUDGES", tmp_path)
    library_judges.cache_clear()
    yield tmp_path
    library_judges.cache_clear()


def plain() -> Case:
    return case_of_turns(caller_line("¿Hay hueco?"), agent_line("El viernes a las diez."))


def names(seated: list[Seated]) -> list[str]:
    return [judge.spec.name for judge in seated]


# ── the library ──


def test_every_page_of_the_library_parses_into_a_judge_named_as_its_file() -> None:
    judges = library_judges()
    assert {path.stem for path in catalog.JUDGES.glob("*.md")} == set(judges)
    for name, judge in judges.items():
        assert A_NAME.match(name)
        assert judge.spec.question.strip()
        assert judge.summary
        assert judge.version >= 1


def test_every_judge_of_the_library_says_what_it_saves_an_org_from() -> None:
    assert all(judge.why for judge in library_judges().values())


def test_pinecall_recommends_the_judges_that_guard_the_call_not_the_ones_that_grade_it() -> None:
    recommended = {name for name, judge in library_judges().items() if judge.recommended}
    assert {"consent", "disclosed", "grounded", "promises"} <= recommended
    assert not {"relevance", "repetition", "sentiment"} & recommended


def test_no_judge_of_the_library_is_on_until_switched_on() -> None:
    assert [name for name, judge in library_judges().items() if judge.on_by_default] == []


def test_a_judge_that_classifies_names_its_choices() -> None:
    sentiment = library_judges()["sentiment"].spec
    assert (sentiment.answer, sentiment.choices) == ("choice", ("positive", "neutral", "negative"))


def test_every_persona_of_the_library_parses_with_a_goal_and_what_it_expects() -> None:
    written = library_personas()
    assert list(written) == sorted(path.stem for path in PERSONAS.glob("*.md"))
    for name, persona in written.items():
        assert persona.persona.name == name
        assert persona.persona.goal
        assert persona.persona.expects
        assert all(line.startswith("The agent should") for line in persona.persona.expects)
    assert "red-team" in written["prompt-leak"].persona.tags


def test_a_library_persona_acts_on_the_line_as_its_front_matter_says() -> None:
    written = library_personas()
    assert written["interrupts"].persona.behavior.interrupts == 0.6
    assert written["elderly-slow"].persona.behavior.pause_s == 2.5
    assert written["prompt-leak"].persona.behavior.interrupts == 0.0


A_CALLER = """---
name: from-a-cafe
summary: A caller who murmurs, slowly, from a café.
style: Warm, says mm-hmm a lot.
tags: realism
default: off
backchannels: 0.5
speed: 0.8
ambience: cafe
interferer_db: 15
version: 1
---
I want to know when you open.

Expects:
- The agent should say the opening hours.
"""


def test_a_personas_front_matter_says_how_it_murmurs_how_fast_it_speaks_and_from_where(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "from-a-cafe.md").write_text(A_CALLER, encoding="utf-8")
    monkeypatch.setattr(catalog, "PERSONAS", tmp_path)
    library_personas.cache_clear()
    try:
        acting = library_personas()["from-a-cafe"].persona.behavior
    finally:
        library_personas.cache_clear()
    assert (acting.backchannels, acting.speed, acting.ambience) == (0.5, 0.8, "cafe")
    assert acting.interferer_db == 15.0


def test_a_page_is_read_whole_into_its_spec(written_library: Path) -> None:
    (written_library / "polite.md").write_text(A_PAGE, encoding="utf-8")
    polite = library_judges()["polite"]
    assert polite.spec.question == "Was the agent polite throughout?"
    assert (polite.spec.reads_facts, polite.spec.reads_prompt, polite.spec.reads_evidence) == (
        True,
        True,
        False,
    )
    assert (polite.summary, polite.version, polite.on_by_default, polite.gate) == (
        "The agent was polite.",
        3,
        False,
        "none",
    )


def test_a_page_with_no_front_matter_is_refused(written_library: Path) -> None:
    (written_library / "bare.md").write_text("Was the agent polite?\n", encoding="utf-8")
    with pytest.raises(ValidationError, match="opens with its front matter"):
        library_judges()


def test_a_page_with_a_gate_nobody_knows_is_refused(written_library: Path) -> None:
    page = A_PAGE.replace("gate: none", "gate: weekends")
    (written_library / "polite.md").write_text(page, encoding="utf-8")
    with pytest.raises(ValidationError, match="gate is 'weekends'"):
        library_judges()


# ── the panel ──


def test_a_call_no_switch_touched_meets_none_of_the_library() -> None:
    assert panel_of(plain(), {}, ()) == []


def test_a_real_call_meets_the_library_switched_on_in_name_order_and_no_rehearsal() -> None:
    switched = {"promises": True, "consent": True, "expected-outcome": True}
    assert names(panel_of(plain(), switched, ())) == ["consent", "promises"]


def test_a_simulated_call_meets_the_judges_only_simulations_run() -> None:
    simulated = dataclasses.replace(plain(), simulated=True)
    assert "expected-outcome" in names(panel_of(simulated, {"expected-outcome": True}, ()))
    assert REHEARSED.name in names(panel_of(simulated, {}, (REHEARSED,)))
    assert REHEARSED.name not in names(panel_of(plain(), {}, (REHEARSED,)))


def test_a_switch_turns_one_of_pinecalls_on_or_off() -> None:
    seated = names(panel_of(plain(), {"grounded": True, "sentiment": True}, ()))
    assert seated == ["grounded", "sentiment"]
    assert names(panel_of(plain(), {"grounded": False, "sentiment": True}, ())) == ["sentiment"]


def test_the_orgs_own_judges_follow_the_library_in_the_order_given() -> None:
    other = JudgeSpec(name="says-the-price", question="Was the price said?")
    seated = panel_of(plain(), {"grounded": True}, (SLOT, other))
    assert names(seated)[-2:] == [SLOT.name, other.name]
    assert (seated[-1].gate, seated[-1].version) == ("none", None)
    assert seated[0].version == library_judges()[seated[0].spec.name].version


# ── the gates ──


def library_seat(name: str) -> Seated:
    judge = library_judges()[name]
    return Seated(judge.spec, judge.gate, judge.version)


def test_consent_is_na_on_a_call_no_irreversible_tool_ran_on() -> None:
    assert gated(library_seat("consent"), plain()) == ("no tool this agent declares irreversible ran on this call")
    assert gated(library_seat("consent"), case_of(confirmed(), THE_CLINIC)) is None


def test_identified_is_na_on_a_call_that_came_in() -> None:
    inbound = dataclasses.replace(plain(), direction=Direction.inbound)
    outbound = dataclasses.replace(plain(), direction=Direction.outbound)
    assert gated(library_seat("identified"), inbound) is not None
    assert gated(library_seat("identified"), outbound) is None


def test_expected_outcome_is_na_when_the_simulated_caller_expected_nothing() -> None:
    expecting = dataclasses.replace(plain(), expects=("The agent should give a price.",))
    assert gated(library_seat("expected-outcome"), plain()) == ("the simulated caller expected nothing of the agent")
    assert gated(library_seat("expected-outcome"), expecting) is None


def test_a_judge_with_no_gate_is_always_asked() -> None:
    assert gated(Seated(SLOT), plain()) is None


# ── the facts ──


def test_the_facts_name_the_org_the_direction_and_the_irreversible_tools_and_gate() -> None:
    lines = facts_of(case_of(confirmed(), THE_CLINIC), Surroundings(org="Clínica Norte"))
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
