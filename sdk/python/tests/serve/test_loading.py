"""What serve is told and loads: flags by place, a state by field, the class from its folder."""

from pathlib import Path

import pytest

from pinecall.serve._loading import CannotServe, Served, as_state, load_served, parse
from tests.fakes.project import written


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
    assert (
        load_served(Served(written(tmp_path / "a", "front-desk"), "front-desk")).slug
        == "front-desk"
    )
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
