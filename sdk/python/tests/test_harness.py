"""The judges and personas a class owns: built or refused by sentence, `own` sent as declared."""

import pytest

from pinecall import Agent, DeclarationRefused, judges, own_judge, own_persona, personas
from pinecall._harness import harness_of
from pinecall.bridge import config_of
from pinecall.wire.judging import PersonasDeclared

OFFERS = own_judge(
    name="offers-next-slot",
    asks="Did the agent offer the next free slot before the caller asked twice?",
    reads=["facts"],
)

RUSH = own_persona(
    name="in-a-rush",
    goal="book today",
    style="short, interrupts",
    expects=["The agent should offer today."],
    behavior={"interrupts": 0.3, "pause_s": 1},
)


def test_a_judge_of_the_agents_own_is_its_question_with_how_and_when_filled_in() -> None:
    assert OFFERS == {
        "name": "offers-next-slot",
        "question": "Did the agent offer the next free slot before the caller asked twice?",
        "answer": "verdict",
        "choices": [],
        "when": "always",
        "trigger": "",
        "reads": ["facts"],
    }


def test_a_judge_answers_one_of_several_on_a_trigger_reading_what_it_was_told_to() -> None:
    read = own_judge(
        name="reason",
        asks="Why did they call?",
        answer="choice",
        choices=["book", "cancel"],
        when="trigger",
        trigger="Did the caller say why?",
        reads=["prompt", "evidence"],
    )

    assert (read["answer"], read["choices"], read["when"], read["trigger"], read["reads"]) == (
        "choice",
        ["book", "cancel"],
        "trigger",
        "Did the caller say why?",
        ["prompt", "evidence"],
    )


@pytest.mark.parametrize(
    ("given", "sentence"),
    [
        ({"name": "offers", "asks": " "}, "offers: a judge asks a question of a call"),
        (
            {"name": "offers", "asks": "Q?", "answer": "maybe"},
            'offers: answer is "maybe", not one of verdict, choice, score',
        ),
        (
            {"name": "offers", "asks": "Q?", "answer": "choice", "choices": ["a"]},
            "offers: a judge that answers one of several needs at least two choices",
        ),
        (
            {"name": "offers", "asks": "Q?", "choices": ["a", "b"]},
            "offers: only a judge that answers one of several takes choices",
        ),
        (
            {"name": "offers", "asks": "Q?", "when": "trigger"},
            "offers: a judge that runs on a trigger needs the trigger's question",
        ),
        (
            {"name": "offers", "asks": "Q?", "reads": ["dreams"]},
            'offers: reads is "dreams", not one of prompt, evidence, facts',
        ),
        (
            {"name": "Offers Slot", "asks": "Q?"},
            '"Offers Slot" is not a judge\'s name: lower-case words joined by hyphens',
        ),
    ],
)
def test_a_judge_that_is_wrong_is_refused_by_sentence(
    given: dict[str, object], sentence: str
) -> None:
    with pytest.raises(DeclarationRefused, match=sentence.replace("(", r"\(").replace(")", r"\)")):
        own_judge(**given)  # type: ignore[arg-type]


def test_a_persona_of_the_agents_own_is_what_a_put_takes_under_its_name() -> None:
    assert (RUSH["name"], RUSH["goal"], RUSH["expects"]) == (
        "in-a-rush",
        "book today",
        ["The agent should offer today."],
    )
    behavior = RUSH["behavior"]
    assert isinstance(behavior, dict)
    assert (behavior["interrupts"], behavior["pause_s"]) == (0.3, 1.0)


@pytest.mark.parametrize(
    ("given", "sentence"),
    [
        (
            {"name": "in-a-rush", "goal": " ", "style": "s"},
            "in-a-rush: a persona wants something: write its goal, in the first person",
        ),
        (
            {"name": "in-a-rush", "goal": "g", "style": ""},
            "in-a-rush: a persona talks some way: write its style",
        ),
        (
            {"name": "in-a-rush", "goal": "g", "style": "s", "behavior": {"interrupts": 3}},
            "in-a-rush: behavior.interrupts",
        ),
        ({"name": "In A Rush", "goal": "g", "style": "s"}, '"In A Rush" is not a persona\'s name'),
    ],
)
def test_a_persona_that_is_wrong_is_refused_by_sentence(
    given: dict[str, object], sentence: str
) -> None:
    with pytest.raises(DeclarationRefused, match=sentence):
        own_persona(**given)  # type: ignore[arg-type]


def test_what_the_class_owns_is_its_switches_plus_its_own_as_the_declaration_sends_it() -> None:
    class Owns(Agent):
        """Owns its judges and its personas."""

        judges = judges(on=["consent", "grounded"], own=[OFFERS])
        personas = personas(on=["in-a-hurry"], own=[RUSH])

    declared = harness_of(Owns)

    assert declared["judges"] == {"on": ["consent", "grounded"], "own": [OFFERS]}
    callers = PersonasDeclared.model_validate(declared["personas"])
    assert ([one.name for one in callers.own], callers.on) == (["in-a-rush"], ["in-a-hurry"])
    assert config_of(Owns).model_dump(exclude_none=True)["judges"] == declared["judges"]


def test_a_class_that_declares_neither_leaves_both_to_the_org() -> None:
    class Silent(Agent):
        """Declares neither."""

    assert harness_of(Silent) == {}
    assert "judges" not in config_of(Silent).model_dump(exclude_none=True)


def test_a_class_that_declares_them_with_none_of_its_own_owns_an_empty_list_and_its_switches() -> (
    None
):
    class Bare(Agent):
        """None but Pinecall's."""

        judges = judges()
        personas = personas(on=["interrupts"])

    sent = config_of(Bare).model_dump(exclude_none=True)

    assert sent["judges"] == {"on": [], "own": []}
    assert sent["personas"] == {"on": ["interrupts"], "own": []}


def test_two_of_one_name_and_an_own_written_as_a_plain_dict_that_is_wrong_are_refused() -> None:
    with pytest.raises(DeclarationRefused, match="two judges called offers-next-slot"):
        judges(own=[OFFERS, OFFERS])
    with pytest.raises(DeclarationRefused, match="two personas called in-a-rush"):
        personas(own=[RUSH, dict(RUSH)])
    with pytest.raises(DeclarationRefused, match="offers-next-slot: answer"):
        judges(own=[{**OFFERS, "answer": "maybe"}])
    with pytest.raises(DeclarationRefused, match="it: name"):
        personas(own=[{"goal": "g", "style": "s"}])
