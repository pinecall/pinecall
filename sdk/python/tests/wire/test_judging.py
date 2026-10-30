"""The judges and the personas a class declares, as the wire carries them: defaults and refusals."""

import pytest
from pydantic import ValidationError

from pinecall.wire.judging import (
    JudgeDeclaration,
    JudgesDeclared,
    PersonaDeclaration,
    PersonasDeclared,
)


def test_a_judge_declared_with_a_name_and_a_question_alone_is_a_verdict_on_every_call() -> None:
    judge = JudgeDeclaration(name="offers-next-slot", question="Offered?")

    assert (judge.answer, judge.when, judge.choices, judge.reads) == ("verdict", "always", [], [])
    assert JudgesDeclared().model_dump() == {"on": [], "own": []}


def test_a_persona_declared_with_a_goal_and_a_style_is_a_quiet_caller_on_the_runtimes_models() -> (
    None
):
    persona = PersonaDeclaration(name="in-a-rush", goal="book today", style="short")

    assert (persona.behavior.interrupts, persona.behavior.ambience) == (0.0, "television")
    assert (persona.llm, persona.expects, persona.facts) == (None, [], {})
    assert PersonasDeclared(own=[persona]).own[0].name == "in-a-rush"


def test_a_share_outside_its_bound_and_a_key_the_wire_does_not_know_are_refused() -> None:
    with pytest.raises(ValidationError):
        PersonaDeclaration(name="x", goal="g", style="s", behavior={"interrupts": 2})  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        JudgeDeclaration.model_validate({"name": "x", "question": "q", "mood": "x"})
