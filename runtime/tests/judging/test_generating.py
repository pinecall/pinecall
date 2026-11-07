"""The scenarist: a library caller is given the one thing it phones this agent about, and keeps its manner."""

from pinecall_runtime.judging.service.generating import Brief, write_scenario
from pinecall_runtime.judging.service.specs import Behavior, Persona
from tests.judging.factories import answering, prompts_of

ELDERLY = Persona(
    name="elderly-slow",
    goal="I want help with what this business offers, but I need things explained slowly and twice.",
    style="Long pauses, asks for things to be said again.",
    facts={"name": "Rosa"},
    expects=("The agent should repeat key details when asked.",),
    behavior=Behavior(pause_s=2.5),
)
A_CLINIC = Brief(
    prompt="You answer the phone for Clínica Norte, a dental clinic. You book cleanings and check-ups.",
    tools=("book: books a visit",),
)


async def test_the_caller_phones_about_what_this_agent_does_and_keeps_how_it_talks() -> None:
    model = answering(
        {
            "name": "brief_caller",
            "arguments": {
                "goal": "Quiero una limpieza dental para la semana que viene.",
                "facts": {"last visit": "hace un año"},
            },
        }
    )
    briefed, usage = await write_scenario(model, A_CLINIC, ELDERLY)
    assert briefed.goal == "Quiero una limpieza dental para la semana que viene."
    assert briefed.facts == {"name": "Rosa", "last visit": "hace un año"}
    assert (briefed.style, briefed.expects, briefed.behavior) == (ELDERLY.style, ELDERLY.expects, ELDERLY.behavior)
    assert usage is not None
    asked = prompts_of(model)[0]
    assert "Clínica Norte" in asked and "book: books a visit" in asked and ELDERLY.style in asked


async def test_a_scenarist_that_hands_in_no_goal_leaves_the_caller_as_it_came() -> None:
    model = answering({"name": "brief_caller", "arguments": {"goal": "  "}})
    briefed, _ = await write_scenario(model, A_CLINIC, ELDERLY)
    assert briefed == ELDERLY
