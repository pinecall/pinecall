"""The library of judges and personas: every page of Pinecall's parses, and a page is read whole or refused."""

from pathlib import Path

import pytest

from runtime.exceptions import ValidationError
from runtime.judging.service.library import (
    JUDGES,
    PERSONAS,
    library_judges,
    library_personas,
    read_judge,
    read_persona,
)
from runtime.judging.service.specs import A_NAME

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


def written(folder: Path, name: str, page: str) -> Path:
    """A page of the test's own, in a folder of its own."""
    path = folder / f"{name}.md"
    path.write_text(page, encoding="utf-8")
    return path


# ── the library ──


def test_every_page_of_the_library_parses_into_a_judge_named_as_its_file() -> None:
    judges = library_judges()
    assert {path.stem for path in JUDGES.glob("*.md")} == set(judges)
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


def test_a_personas_front_matter_says_how_it_murmurs_how_fast_it_speaks_and_from_where(tmp_path: Path) -> None:
    acting = read_persona(written(tmp_path, "from-a-cafe", A_CALLER)).persona.behavior
    assert (acting.backchannels, acting.speed, acting.ambience) == (0.5, 0.8, "cafe")
    assert acting.interferer_db == 15.0


def test_a_page_is_read_whole_into_its_spec(tmp_path: Path) -> None:
    polite = read_judge(written(tmp_path, "polite", A_PAGE))
    assert polite.spec.question == "Was the agent polite throughout?"
    assert polite.spec.list_reads() == ["prompt", "facts"]
    assert (polite.summary, polite.version, polite.on_by_default, polite.gate) == (
        "The agent was polite.",
        3,
        False,
        "none",
    )


def test_a_page_with_no_front_matter_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="opens with its front matter"):
        read_judge(written(tmp_path, "bare", "Was the agent polite?\n"))


def test_a_page_with_a_gate_nobody_knows_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="gate is 'weekends'"):
        read_judge(written(tmp_path, "polite", A_PAGE.replace("gate: none", "gate: weekends")))
