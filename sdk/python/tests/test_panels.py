"""Drawing a panel to the console's nodes: the same JSON the TypeScript package's tags give."""

import pytest

from pinecall import Agent, DeclarationRefused, Drawing, Who, panel
from pinecall.panels import Declared, drawn, panel_of


class Mudanzas(Agent):
    """La ficha del cliente, para la consola."""

    def since(self, contact: str) -> str | None:
        """When the client signed up, from the clinic's own systems."""
        return "12 Mar 2024" if contact == "+34600" else None

    @panel("Ficha del cliente")
    def ficha(self, who: Who, draw: Drawing) -> None:
        """The client's card."""
        with draw.panel("Cliente"), draw.rows():
            draw.row("Alta", self.since(who.contact))
            draw.row("Zona", "Centro")


WHO = Who(agent="mudanzas", contact="+34600", call="CA_1")


def nodes_of(drawing: Drawing) -> list[dict[str, object]]:
    return drawing.nodes


def test_a_panel_is_one_node_with_its_children_under_it_and_the_classs_helpers_at_hand() -> None:
    declared = panel_of(Mudanzas)
    assert declared == Declared("Ficha del cliente", "ficha")
    assert drawn(Mudanzas, Declared("Ficha del cliente", "ficha"), WHO) == {
        "name": "Ficha del cliente",
        "nodes": [
            {
                "tag": "panel",
                "title": "Cliente",
                "children": [
                    {
                        "tag": "rows",
                        "children": [
                            {"tag": "row", "label": "Alta", "value": "12 Mar 2024"},
                            {"tag": "row", "label": "Zona", "value": "Centro"},
                        ],
                    }
                ],
            }
        ],
    }


def test_an_async_panel_is_drawn_to_its_end() -> None:
    class Remota(Agent):
        """Lee su ficha de lejos."""

        @panel("Remota")
        async def ficha(self, who: Who, draw: Drawing) -> None:
            draw.text(f"para {who.contact}")

    declared = panel_of(Remota)
    assert declared is not None
    assert drawn(Remota, declared, WHO)["nodes"] == [{"tag": "text", "text": "para +34600"}]


def test_a_number_is_written_out_wherever_it_is() -> None:
    drawing = Drawing()
    drawing.stat("Servicios", 3)
    drawing.stat("Media", 2.5)
    drawing.stat("Total", 240.0)
    assert [node["value"] for node in nodes_of(drawing)] == ["3", "2.5", "240"]


def test_a_tables_rows_are_read_by_the_columns_own_names_or_in_their_order() -> None:
    drawing = Drawing()
    drawing.table(
        ["fecha", "servicio", "importe"],
        [{"fecha": "12 Mar", "servicio": "Mudanza", "importe": 240}],
    )
    drawing.table(["a", "b"], [("uno", "dos")])
    assert nodes_of(drawing) == [
        {
            "tag": "table",
            "columns": ["fecha", "servicio", "importe"],
            "rows": [["12 Mar", "Mudanza", "240"]],
        },
        {"tag": "table", "columns": ["a", "b"], "rows": [["uno", "dos"]]},
    ]


def test_a_badge_keeps_its_tone_and_one_it_does_not_know_is_neutral() -> None:
    drawing = Drawing()
    drawing.badge("con saldo", tone="warn")
    drawing.badge("al día", tone="turquoise")
    assert nodes_of(drawing) == [
        {"tag": "badge", "tone": "warn", "text": "con saldo"},
        {"tag": "badge", "tone": "neutral", "text": "al día"},
    ]


def test_what_the_view_left_out_draws_nothing_and_none_and_booleans_say_nothing() -> None:
    drawing = Drawing()
    with drawing.panel():
        drawing.text("")
    drawing.row("Activo", True)  # noqa: FBT003 - a boolean is a value the console shows as nothing
    assert nodes_of(drawing) == [
        {"tag": "panel", "title": None, "children": []},
        {"tag": "row", "label": "Activo", "value": ""},
    ]


def test_a_class_draws_one_panel_and_a_subclass_inherits_none() -> None:
    def ficha(self: Agent, who: Who, draw: Drawing) -> None: ...

    def otra(self: Agent, who: Who, draw: Drawing) -> None: ...

    body = {"__doc__": "Dos paneles.", "ficha": panel("Ficha")(ficha), "otra": panel("Otra")(otra)}
    with pytest.raises(
        DeclarationRefused, match=r"declares two panels \(Ficha and Otra\); a class draws one panel"
    ):
        type("Doble", (Agent,), body)

    class Hija(Mudanzas):
        """Sin panel propio."""

    assert panel_of(Hija) is None


def test_a_panel_that_does_not_draw_with_who_and_draw_is_refused() -> None:
    def ficha(self: Agent) -> None: ...

    with pytest.raises(DeclarationRefused, match="a panel draws with"):
        type("Mala", (Agent,), {"__doc__": "Mal.", "ficha": panel("Ficha")(ficha)})
