"""The judges and the personas a class owns: the switches, the files, each refusal a sentence."""

import json
from pathlib import Path

import pytest

from pinecall import Agent, DeclarationRefused, judges, personas
from pinecall._harness import harness_of, judge_of, persona_of
from pinecall.bridge import config_of
from pinecall.wire.judging import PersonasDeclared

OFFERS = """---
answer: verdict
when: always
reads: [facts]
---
Did the agent offer the next free slot before the caller asked twice?
"""

RUSH = json.dumps(
    {
        "goal": "book today",
        "style": "short, interrupts",
        "expects": ["The agent should offer today."],
        "behavior": {"interrupts": 0.3, "pause_s": 1},
    }
)


def folder(tmp_path: Path, files: dict[str, str]) -> Path:
    """A folder shaped like `agents/<slug>/`, with files under `judges/` and `test/personas/`."""
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return tmp_path


def test_a_judge_file_is_read_as_the_library_writes_one() -> None:
    read = judge_of(Path("judges/offers-next-slot.md"), OFFERS)

    assert read.model_dump() == {
        "name": "offers-next-slot",
        "question": "Did the agent offer the next free slot before the caller asked twice?",
        "answer": "verdict",
        "choices": [],
        "when": "always",
        "trigger": "",
        "reads": ["facts"],
    }


def test_a_judge_file_takes_the_librarys_on_for_when_and_a_comma_separated_list() -> None:
    read = judge_of(
        Path("x.md"), "---\non: simulations\nreads: prompt, evidence\n---\nWas it kind?"
    )

    assert (read.when, read.reads) == ("simulations", ["prompt", "evidence"])


@pytest.mark.parametrize(
    ("file", "text", "sentence"),
    [
        (
            "offers.md",
            "no front matter\n",
            "a judge opens with its front matter between two --- lines",
        ),
        (
            "offers.md",
            "---\n\n---\n\n",
            "a judge asks a question of a call: write one below the front matter",
        ),
        (
            "offers.md",
            "---\nanswer: maybe\n---\nQ?",
            'answer is "maybe", not one of verdict, choice, score',
        ),
        ("offers.md", "---\nanswer: choice\nchoices: [a]\n---\nQ?", "needs at least two choices"),
        (
            "offers.md",
            "---\nchoices: [a, b]\n---\nQ?",
            "only a judge that answers one of several takes choices",
        ),
        (
            "offers.md",
            "---\nwhen: trigger\n---\nQ?",
            "a judge that runs on a trigger needs the trigger's question",
        ),
        (
            "offers.md",
            "---\nreads: dreams\n---\nQ?",
            'reads is "dreams", not one of prompt, evidence, facts',
        ),
        (
            "Offers Slot.md",
            "---\n\n---\nQ?",
            '"Offers Slot" is not a judge\'s name: lower-case words joined by hyphens',
        ),
        (
            "offers.md",
            "---\nname: other\n---\nQ?",
            "its front matter says name: other, and the file is offers.md",
        ),
    ],
)
def test_a_judge_file_that_is_wrong_is_refused_by_sentence(
    file: str, text: str, sentence: str
) -> None:
    with pytest.raises(DeclarationRefused, match=sentence.replace("(", r"\(").replace(")", r"\)")):
        judge_of(Path(file), text)


def test_a_persona_file_is_what_a_put_takes_under_the_files_name() -> None:
    read = persona_of(Path("test/personas/in-a-rush.json"), RUSH)

    assert (read.name, read.goal, read.expects) == (
        "in-a-rush",
        "book today",
        ["The agent should offer today."],
    )
    assert (read.behavior.interrupts, read.behavior.pause_s) == (0.3, 1.0)


@pytest.mark.parametrize(
    ("file", "text", "sentence"),
    [
        ("in-a-rush.json", "{", "not JSON"),
        ("in-a-rush.json", "[]", "a persona is a JSON object with a goal and a style"),
        (
            "in-a-rush.json",
            '{"style": "s"}',
            "a persona wants something: write its goal, in the first person",
        ),
        ("in-a-rush.json", '{"goal": "g"}', "a persona talks some way: write its style"),
        (
            "in-a-rush.json",
            '{"goal": "g", "style": "s", "name": "other"}',
            "it says its name is other",
        ),
        ("in-a-rush.json", '{"goal": "g", "style": "s", "mood": "x"}', "mood"),
        ("In A Rush.json", "{}", '"In A Rush" is not a persona\'s name'),
    ],
)
def test_a_persona_file_that_is_wrong_is_refused_by_sentence(
    file: str, text: str, sentence: str
) -> None:
    with pytest.raises(DeclarationRefused, match=sentence):
        persona_of(Path(file), text)


def test_what_the_class_owns_is_its_switches_plus_the_folders_beside_it(tmp_path: Path) -> None:
    class Owns(Agent):
        """Owns its judges and its personas."""

        judges = judges(on=["consent", "grounded"])
        personas = personas(on=["in-a-hurry"])

    where = folder(
        tmp_path, {"judges/offers-next-slot.md": OFFERS, "test/personas/in-a-rush.json": RUSH}
    )
    declared = harness_of(Owns, where)

    assert declared["judges"] == {
        "on": ["consent", "grounded"],
        "own": [judge_of(Path("x/offers-next-slot.md"), OFFERS).model_dump()],
    }
    callers = PersonasDeclared.model_validate(declared["personas"])
    assert ([one.name for one in callers.own], callers.on) == (["in-a-rush"], ["in-a-hurry"])


def test_a_class_that_declares_nothing_with_no_folder_leaves_both_to_the_org(
    tmp_path: Path,
) -> None:
    class Silent(Agent):
        """Declares neither."""

    assert harness_of(Silent, tmp_path) == {}
    assert harness_of(Silent, None) == {}
    assert "judges" not in config_of(Silent).model_dump(exclude_none=True)


def test_a_class_that_declares_them_with_no_folder_owns_an_empty_list_and_its_switches() -> None:
    class Bare(Agent):
        """None but Pinecall's."""

        judges = judges()
        personas = personas(on=["interrupts"])

    sent = config_of(Bare).model_dump(exclude_none=True)

    assert sent["judges"] == {"on": [], "own": []}
    assert sent["personas"] == {"on": ["interrupts"], "own": []}


def test_a_folder_with_files_the_class_never_declared_is_refused_saying_what_to_write(
    tmp_path: Path,
) -> None:
    class Silent(Agent):
        """Declares neither."""

    with_judges = folder(tmp_path / "a", {"judges/offers-next-slot.md": OFFERS})
    with pytest.raises(
        DeclarationRefused, match=r"holds 1 judge\(s\) and the class declares none: judges = judges"
    ):
        harness_of(Silent, with_judges)
    with_personas = folder(tmp_path / "b", {"test/personas/in-a-rush.json": RUSH})
    with pytest.raises(
        DeclarationRefused, match=r"holds 1 persona\(s\) and the class declares none"
    ):
        harness_of(Silent, with_personas)
