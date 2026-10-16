"""The prompt: four blocks in two regions, static ones that never move, the view that does."""

from typing import Literal

import pytest

from pinecall import Agent, Line, render, show_prompt, tool
from pinecall._author import writing_as
from pinecall._rules import PROTOCOLS, RULES, SPOKEN
from pinecall.blocks import LAYOUT


class Clinica(Agent):
    """Eres la recepción de Clínica Norte.

    Todo lo que dices se lee en voz alta.
    """

    stage: Literal["identify", "book"] = "identify"
    patient: str | None = None
    slots: list[str] = []  # noqa: RUF012 - a field's opening value, copied for every call

    view_template = """
{% if stage == "identify" %}
Saluda y pide nombre y teléfono.
{% endif %}
{% if patient %}
Hablas con {{ patient }}.
{% endif %}

{% if remembers("por la mañana") %}
Ofrécele primero las horas de la mañana.
{% endif %}

{% if slots %}
## Horas libres

{% for slot in slots %}
{{ slot }}
{% endfor %}
{% endif %}


{% if resumed %}
Se cortó su llamada anterior.
{% endif %}
{% if call.claimed %}
Ya ve la página {{ call.claimed }}.
{% endif %}
"""

    @tool(stage="identify")
    def find_patient(self, name: str) -> None:
        """Busca al paciente."""
        self.patient = name
        self.stage = "book"


@pytest.fixture
def clinica() -> Clinica:
    return Clinica().seal()


def test_the_layout_is_the_frameworks_four_blocks_in_send_order(clinica: Clinica) -> None:
    rendered = render(clinica)
    assert [block.name for block in rendered.blocks] == ["identity", "knowledge", "tools", "view"]
    assert [block.region for block in rendered.blocks] == ["static", "static", "static", "dynamic"]
    assert [spec.name for spec in LAYOUT] == ["identity", "knowledge", "tools", "view"]


def test_the_static_blocks_joined_are_one_text_the_docstring_the_words_the_tools(
    clinica: Clinica,
) -> None:
    assert render(clinica).instructions() == "\n\n".join(
        [
            "Eres la recepción de Clínica Norte. Todo lo que dices se lee en voz alta.",
            f"<rules>\n{RULES}\n</rules>",
            f"<protocols>\n{PROTOCOLS}\n</protocols>",
            f"<channel>\n{SPOKEN}\n</channel>",
            "<tools>\n- find_patient: Busca al paciente.\n</tools>",
        ]
    )


def test_the_knowledge_block_is_the_gateways_and_the_class_sends_nothing_for_it(
    clinica: Clinica,
) -> None:
    assert render(clinica)["knowledge"] == ""


def test_the_static_blocks_do_not_move_when_the_state_does(clinica: Clinica) -> None:
    before = [block.text for block in render(clinica).static()]
    clinica.run_tool("find_patient", {"name": "Marta"})
    assert [block.text for block in render(clinica).static()] == before


def test_the_view_block_is_the_view_and_it_moves(clinica: Clinica) -> None:
    assert "Saluda y pide nombre y teléfono." in render(clinica)["view"]
    clinica.run_tool("find_patient", {"name": "Marta"})
    assert "Hablas con Marta." in render(clinica)["view"]
    assert "Saluda" not in render(clinica)["view"]


def test_what_is_remembered_decides_a_sentence_and_never_reaches_a_block(clinica: Clinica) -> None:
    rendered = render(clinica, remembered=["le gusta por la mañana"])
    assert "Ofrécele primero las horas de la mañana." in rendered["view"]
    assert all("le gusta" not in block.text for block in rendered.blocks)
    assert "Ofrécele primero" not in render(clinica)["view"]


def test_the_view_reads_what_surrounds_the_call_and_not_only_the_state(clinica: Clinica) -> None:
    assert "Se cortó su llamada anterior." in render(clinica, resumed=True)["view"]
    assert "Ya ve la página 4821." in render(clinica, Line(claimed="4821"))["view"]


def test_a_template_is_laid_out_for_a_person_and_the_ragged_edges_come_off(
    clinica: Clinica,
) -> None:
    with writing_as("the test"):
        clinica.slots = ["martes 10:00", "martes 11:00"]
    view = render(clinica)["view"]
    assert "## Horas libres\n\nmartes 10:00\nmartes 11:00" in view
    assert "\n\n\n" not in view
    assert view == view.strip()


def test_the_history_carries_the_summaries_a_collapse_left(clinica: Clinica) -> None:
    clinica.run_tool("find_patient", {"name": "Marta"})
    clinica.collapse("La paciente ya está identificada.")
    assert (
        render(clinica).history
        == '<!-- collapsed: {"seq":3} -->\nLa paciente ya está identificada.'
    )


def test_the_page_a_person_reads_names_every_block_and_the_history_between_the_regions(
    clinica: Clinica,
) -> None:
    headers = [line for line in show_prompt(clinica).splitlines() if line.startswith("── ")]
    assert headers == [
        "── identity (static) ──",
        "── knowledge (static) ──",
        "── tools (static) ──",
        "── history ──",
        "── view (dynamic) ──",
    ]


def test_a_class_with_no_view_has_an_empty_dynamic_block_and_no_docstring_no_identity_line() -> (
    None
):
    class Callada(Agent):
        pass

    rendered = render(Callada())
    assert rendered["view"] == ""
    assert rendered["identity"].startswith("<rules>")
    assert rendered["tools"] == ""
