"""A project of one agent written into a folder, laid out as the CLI lays one, for serve's tests."""

from pathlib import Path

AGENT = '''"""La recepción de la clínica."""

from typing import Literal

from pinecall import Agent, Drawing, Who, panel, tool

from .agenda import AGENDA
import agenda as by_name


class Recepcion(Agent):
    """Eres la recepción de la clínica."""

    stage: Literal["identify", "book"] = "identify"
    patient: str | None = None

    @tool(stage="identify")
    def find_patient(self, name: str) -> str:
        """Busca al paciente."""
        self.patient = AGENDA.get(name, name)
        self.stage = "book"
        return self.patient

    @tool(stage="book")
    def book(self, slot: str) -> str:
        """Reserva la hora."""
        return by_name.BOOKED + slot

    @panel("Ficha")
    def ficha(self, who: Who, draw: Drawing) -> None:
        """La ficha."""
        draw.text(f"{who.contact} en {who.call}")
'''

AGENDA = '''"""La agenda de la clínica."""

AGENDA = {"ana": "Ana García"}
BOOKED = "reservado: "
'''

VIEW = """{% if patient %}Hablas con {{ patient }}.{% else %}Pide el nombre.{% endif %}
"""


def written(root: Path, slug: str = "recepcion") -> Path:
    """Write `agents/<slug>/` with its class, a module beside it, and its view; the class's file."""
    folder = root / "agents" / slug
    (folder / "views").mkdir(parents=True)
    (folder / "agent.py").write_text(AGENT, encoding="utf-8")
    (folder / "agenda.py").write_text(AGENDA, encoding="utf-8")
    (folder / "views" / f"{slug}.jinja").write_text(VIEW, encoding="utf-8")
    return folder / "agent.py"
