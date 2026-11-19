"""What serve is told and loads: flags by place, a state by field, a class and its personas."""

import sys
from pathlib import Path

import pytest

from pinecall import DeclarationRefused, _config
from pinecall._harness import harness_of
from pinecall.serve._loading import CannotServe, Served, as_state, load_served, parse
from pinecall.wire.judging import PersonasDeclared
from tests.fakes.project import with_personas, with_personas_in_the_class, written


def test_each_file_is_served_as_the_slug_beside_it_and_the_rest_are_by_name() -> None:
    flags = parse(
        ["--file", "a.py", "--slug", "a", "--file", "b.py", "--slug", "b", "--console", "--events"]
    )
    assert [(str(one.file), one.slug) for one in flags.served] == [("a.py", "a"), ("b.py", "b")]
    assert (flags.console, flags.events, flags.prod) == (True, True, False)


@pytest.mark.parametrize(
    ("argv", "said"),
    [
        (["--file", "a.py"], "one --slug for each --file"),
        (["--file", "a.py", "--slug", "a", "--loud"], "serve has no flag --loud"),
        (["--file", "--slug", "a"], "--file takes a value"),
        (
            ["--file", "a.py", "--slug", "a", "--channel", "fax"],
            "--channel is phone, web or whatsapp",
        ),
    ],
)
def test_what_the_entry_cannot_be_told_is_refused_with_its_sentence(
    argv: list[str], said: str
) -> None:
    with pytest.raises(CannotServe, match=said):
        parse(argv)


def test_a_state_is_a_field_its_equals_and_its_value_as_json() -> None:
    assert as_state('slots=["martes"]') == {"slots": ["martes"]}
    flags = parse(
        ["--file", "a", "--slug", "a", "--state", 'stage="book"', "--state", "patient=null"]
    )
    assert flags.state == {"stage": "book", "patient": None}
    with pytest.raises(CannotServe, match="its value is not JSON"):
        as_state("stage=book")


def test_a_class_loads_from_its_folder_whose_modules_it_imports_relatively_or_by_name(
    tmp_path: Path,
) -> None:
    cls = load_served(Served(written(tmp_path), "recepcion"))
    assert cls.__name__ == "Recepcion"
    assert cls().seal().run_tool("find_patient", {"name": "ana"}) == "Ana García"


def test_the_slug_is_the_folders_and_a_class_that_names_another_is_refused(tmp_path: Path) -> None:
    served = load_served(Served(written(tmp_path / "a", "front-desk"), "front-desk"))
    assert served.slug == "front-desk"
    # An app and a flow name it by that slug.
    assert _config.agent_named("front-desk") is served
    named = written(tmp_path / "b", "otra-carpeta")
    named.write_text(
        named.read_text().replace(
            "class Recepcion(Agent):\n", 'class Recepcion(Agent):\n    slug = "otra"\n'
        )
    )
    with pytest.raises(
        CannotServe, match="says its slug is otra, and it is served as otra-carpeta"
    ):
        load_served(Served(named, "otra-carpeta"))


def test_a_file_that_is_not_there_does_not_load_or_declares_no_agent_says_so(
    tmp_path: Path,
) -> None:
    with pytest.raises(CannotServe, match="no agent at"):
        load_served(Served(tmp_path / "nada.py", "nada"))
    broken = tmp_path / "rota" / "agent.py"
    broken.parent.mkdir()
    broken.write_text('"""Rota."""\nimport no_such_module\n', encoding="utf-8")
    with pytest.raises(CannotServe, match="did not load: ModuleNotFoundError"):
        load_served(Served(broken, "rota"))
    empty = tmp_path / "vacia" / "agent.py"
    empty.parent.mkdir()
    empty.write_text('"""Vacía."""\n', encoding="utf-8")
    with pytest.raises(CannotServe, match=r"declares no pinecall\.Agent"):
        load_served(Served(empty, "vacia"))


def test_the_personas_file_beside_the_class_is_its_personas_and_imports_its_folder_as_it_does(
    tmp_path: Path,
) -> None:
    cls = load_served(Served(with_personas(written(tmp_path)), "recepcion"))

    callers = PersonasDeclared.model_validate(harness_of(cls)["personas"])

    assert callers.on == ["in-a-hurry"]
    assert [(one.name, one.goal) for one in callers.own] == [
        ("ana", "pedir hora"),
        ("con-prisa", "reservado: hoy"),
    ]
    assert callers.own[0].facts == {"su nombre": "Ana García"}


def test_a_class_with_no_personas_file_declares_none(tmp_path: Path) -> None:
    cls = load_served(Served(written(tmp_path), "recepcion"))
    assert harness_of(cls) == {}


def test_each_agents_personas_file_is_a_module_of_its_own_and_none_is_the_module_personas(
    tmp_path: Path,
) -> None:
    before = sys.modules.get("personas")
    front = with_personas(written(tmp_path, "front-desk"))
    back = with_personas(
        written(tmp_path, "back-office"), '"""Nobody of its own."""\n\nON = ["wrong-number"]\n'
    )

    first = load_served(Served(front, "front-desk"))
    second = load_served(Served(back, "back-office"))

    assert harness_of(second)["personas"] == {"on": ["wrong-number"], "own": []}
    assert PersonasDeclared.model_validate(harness_of(first)["personas"]).on == ["in-a-hurry"]
    one = sys.modules["pinecall_agents.front_desk.test.personas"]
    other = sys.modules["pinecall_agents.back_office.test.personas"]
    assert (one.ON, other.ON) == (["in-a-hurry"], ["wrong-number"])
    assert sys.modules.get("personas") is before


def test_personas_in_the_class_and_in_the_file_are_refused_naming_the_class_and_the_file(
    tmp_path: Path,
) -> None:
    file = with_personas_in_the_class(with_personas(written(tmp_path)))

    with pytest.raises(DeclarationRefused) as refused:
        load_served(Served(file, "recepcion"))

    assert str(refused.value) == (
        f"Recepcion declares personas in the class and {file.parent / 'test' / 'personas.py'}"
        " holds them too: the file is their place — take personas out of the class"
    )


def test_a_refusal_names_the_personas_file_from_the_projects_folder_when_it_runs_there(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    file = with_personas_in_the_class(with_personas(written(tmp_path)))
    monkeypatch.chdir(tmp_path)

    with pytest.raises(DeclarationRefused) as refused:
        load_served(Served(file, "recepcion"))

    assert str(refused.value).startswith(
        f"Recepcion declares personas in the class and {Path('agents/recepcion/test/personas.py')}"
        " holds them too"
    )


def test_personas_in_the_class_with_no_file_load_as_they_did(tmp_path: Path) -> None:
    cls = load_served(Served(with_personas_in_the_class(written(tmp_path)), "recepcion"))
    assert harness_of(cls)["personas"] == {"on": ["interrupts"], "own": []}


def test_a_personas_file_that_does_not_load_or_holds_a_wrong_one_says_so(tmp_path: Path) -> None:
    broken = with_personas(written(tmp_path / "a"), '"""Rota."""\nimport no_such_module\n')
    with pytest.raises(CannotServe, match=r"personas\.py did not load: ModuleNotFoundError"):
        load_served(Served(broken, "recepcion"))
    wrong = with_personas(
        written(tmp_path / "b"),
        '"""Mal."""\nfrom pinecall import own_persona\n\n'
        'X = own_persona(name="x", goal=" ", style="s")\n',
    )
    with pytest.raises(DeclarationRefused, match="x: a persona wants something"):
        load_served(Served(wrong, "recepcion"))
    names = with_personas(written(tmp_path / "c"), '"""Mal."""\n\nON = "in-a-hurry"\n')
    with pytest.raises(DeclarationRefused, match="ON names Pinecall's callers that are on"):
        load_served(Served(names, "recepcion"))
