"""The view: a Jinja template beside the class, the state in scope, an unknown name refused."""

import importlib.util
import sys
from pathlib import Path

import pytest
from jinja2 import UndefinedError

from pinecall import Agent, Line, render
from pinecall._view import rendered, tidy


def view_of(template: str, state: dict[str, object], remembered: tuple[str, ...] = ()) -> str:
    cls = type("Vista", (Agent,), {"__doc__": "Una vista.", "view_template": template})
    return rendered(cls, state, Line(), resumed=False, remembered=remembered)


def test_every_state_field_is_in_scope_by_its_own_name() -> None:
    assert (
        view_of("Hablas con {{ patient }}.", {"patient": "Marta Ruiz"}) == "Hablas con Marta Ruiz."
    )


def test_a_name_the_class_never_declared_is_refused_rather_than_read_as_nothing() -> None:
    with pytest.raises(UndefinedError, match="paciente"):
        view_of("{{ paciente }}", {})


def test_what_is_remembered_decides_a_sentence_and_is_never_printed() -> None:
    template = '{% if remembers("médico habitual") %}\nOfrece sus horas.\n{% endif %}'
    text = view_of(template, {}, ("su médico habitual es la doctora Vidal",))
    assert text == "Ofrece sus horas."
    assert view_of(template, {}) == ""


def test_a_template_is_read_by_a_person_and_the_ragged_edges_come_off_for_the_model() -> None:
    assert tidy("\n\n Hola.   \n\n\n\n  Adiós.  \n\n") == "Hola.\n\n  Adiós."


def test_a_class_reads_the_view_beside_its_file_and_includes_from_its_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "views").mkdir()
    (tmp_path / "views" / "recepcion.jinja").write_text(
        "{% include 'saludo.jinja' %}\nHablas con {{ patient }}.\n", encoding="utf-8"
    )
    (tmp_path / "views" / "saludo.jinja").write_text("Buenos días.\n", encoding="utf-8")
    (tmp_path / "agent.py").write_text(
        '"""La recepción."""\nfrom pinecall import Agent\n\n'
        "class Recepcion(Agent):\n"
        '    """Una recepción."""\n\n'
        "    patient: str | None = 'Ana'\n",
        encoding="utf-8",
    )
    spec = importlib.util.spec_from_file_location("recepcion_agent", tmp_path / "agent.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "recepcion_agent", module)
    spec.loader.exec_module(module)
    assert render(module.Recepcion())["view"] == "Buenos días.\nHablas con Ana."


def test_a_subclass_with_no_view_of_its_own_renders_its_parents() -> None:
    class Padre(Agent):
        """Con vista."""

        view_template = "La vista del padre."

    class Hija(Padre):
        """Sin vista propia."""

    assert render(Hija())["view"] == "La vista del padre."
