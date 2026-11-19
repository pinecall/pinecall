"""The judges a class owns and the personas its file holds: built, or refused by sentence."""

from typing import cast

import pytest

from pinecall import Agent, DeclarationRefused, judges, own_judge, own_persona, personas
from pinecall._harness import file_personas, harness_of, personas_in_the_class
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


def test_a_personas_file_holds_every_own_persona_at_its_top_level_and_the_names_that_are_on() -> (
    None
):
    class Filed(Agent):
        """Its callers are in its test folder."""

        judges = judges(on=["consent"], own=[OFFERS])

    waits = own_persona(name="waits", goal="hold the line", style="patient")
    written: dict[str, object] = {
        "__doc__": "The callers.",
        "own_persona": own_persona,
        "ON": ["in-a-hurry", "wrong-number"],
        "RUSH": RUSH,
        "_waits": waits,
        "AGAIN": RUSH,
        "IN_A_LIST": [own_persona(name="in-a-list", goal="g", style="s")],
        "A_PLAIN_DICT": {"name": "plain", "goal": "g", "style": "s"},
    }

    file_personas(Filed, written, "agents/filed/test/personas.py")
    declared = harness_of(Filed)

    assert declared["judges"] == {"on": ["consent"], "own": [OFFERS]}
    assert declared["personas"] == {"on": ["in-a-hurry", "wrong-number"], "own": [RUSH, waits]}
    assert config_of(Filed).model_dump(exclude_none=True)["personas"]["on"] == [
        "in-a-hurry",
        "wrong-number",
    ]
    assert not personas_in_the_class(Filed)


def test_a_personas_file_with_no_on_switches_none_of_pinecalls_on() -> None:
    class Quiet(Agent):
        """Its file names none of Pinecall's."""

    class Empty(Agent):
        """Its file holds nothing."""

    file_personas(Quiet, {"RUSH": RUSH}, "test/personas.py")
    file_personas(Empty, {}, "test/personas.py")

    assert harness_of(Quiet)["personas"] == {"on": [], "own": [RUSH]}
    assert harness_of(Empty)["personas"] == {"on": [], "own": []}


def test_what_the_file_holds_is_sent_as_plain_dicts_and_no_subclass_inherits_it() -> None:
    class Base(Agent):
        """Its file holds one."""

    file_personas(Base, {"RUSH": RUSH}, "test/personas.py")

    class Another(Base):
        """Another agent, with a folder and no file of its own."""

    own = cast("dict[str, list[object]]", harness_of(Base)["personas"])["own"]
    assert [type(one) for one in own] == [dict]
    assert harness_of(Another) == {}


@pytest.mark.parametrize("on", ["in-a-hurry", ("in-a-hurry",), ["in-a-hurry", 3], None])
def test_on_that_is_not_a_list_of_names_is_refused_naming_the_file(on: object) -> None:
    class Wrong(Agent):
        """Its file's ON is not a list of names."""

    with pytest.raises(DeclarationRefused) as refused:
        file_personas(Wrong, {"ON": on}, "agents/wrong/test/personas.py")

    assert str(refused.value) == (
        "agents/wrong/test/personas.py: ON names Pinecall's callers that are on, "
        'as a list of their names: ON = ["in-a-hurry"]'
    )
    assert harness_of(Wrong) == {}


def test_two_callers_of_one_name_in_the_file_are_refused_as_two_in_own_are() -> None:
    class Twice(Agent):
        """Its file names one caller twice."""

    again = own_persona(name="in-a-rush", goal="book tomorrow", style="slow")

    with pytest.raises(DeclarationRefused, match="two personas called in-a-rush"):
        file_personas(Twice, {"RUSH": RUSH, "AGAIN": again}, "test/personas.py")


def test_a_class_that_declares_personas_and_has_the_file_too_is_refused_for_the_file() -> None:
    class Both(Agent):
        """Declares its callers, and has the file."""

        personas = personas(on=["in-a-hurry"])

    with pytest.raises(DeclarationRefused) as refused:
        file_personas(Both, {"RUSH": RUSH}, "agents/both/test/personas.py")

    assert str(refused.value) == (
        "Both declares personas in the class and agents/both/test/personas.py holds them too: "
        "the file is their place — take personas out of the class"
    )
    # Refused whole: what the class declares is still all it has.
    assert harness_of(Both)["personas"] == {"on": ["in-a-hurry"], "own": []}


def test_a_class_that_still_declares_its_personas_is_known_and_one_that_declares_none_is_not() -> (
    None
):
    class InTheClass(Agent):
        """Declares its callers itself."""

        personas = personas(own=[RUSH])

    class Neither(Agent):
        """Declares none."""

    assert personas_in_the_class(InTheClass)
    assert not personas_in_the_class(Neither)


def test_personas_in_the_class_that_are_not_what_personas_builds_are_sent_to_the_file() -> None:
    class Loose(Agent):
        """Its callers are bare names."""

        personas = ("in-a-hurry",)

    class LooseJudges(Agent):
        """Its judges are bare names."""

        judges = ("consent",)

    with pytest.raises(DeclarationRefused, match=r"personas are declared in test/personas\.py"):
        harness_of(Loose)
    with pytest.raises(DeclarationRefused, match="judges are declared in the class with judges"):
        harness_of(LooseJudges)
