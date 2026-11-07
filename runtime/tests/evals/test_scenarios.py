"""Whom a simulation briefs before it phones: a caller of the library, on an agent that says anything of itself."""

from pinecall_runtime.evals.service import as_scenario, is_the_librarys, says_anything
from pinecall_runtime.judging import service as judging


def test_only_a_caller_of_the_library_is_briefed() -> None:
    assert is_the_librarys(judging.CallerPersona(name="elderly-slow", goal="help", style="slow"))
    assert not is_the_librarys(judging.CallerPersona(name="marta-cancels", goal="cancel", style="curt"))


def test_an_agent_nobody_has_called_with_no_tools_is_nothing_to_brief_on() -> None:
    assert not says_anything(judging.Brief())
    assert says_anything(judging.Brief(tools=("book: books a visit",)))
    assert says_anything(judging.Brief(prompt="You answer for a clinic."))


def test_a_scenario_given_is_what_the_caller_phones_about_with_its_facts_over_its_own() -> None:
    caller = judging.CallerPersona(name="elderly-slow", goal="help", style="slow", facts={"name": "Rosa", "age": "81"})
    moved = "I want to move my visit of Tuesday to the afternoon."
    phoned = as_scenario(caller, moved, {"visit": "Tuesday 9:00", "age": "82"})
    assert phoned.goal == moved
    assert phoned.facts == {"name": "Rosa", "age": "82", "visit": "Tuesday 9:00"}
    assert phoned.style == "slow"
    assert caller.goal == "help"
