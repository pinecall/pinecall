"""Ring 0: a class held as a call holds it, driven by a test, with no network and no key."""

from typing import Literal

from typing_extensions import override

from pinecall import Agent, CallWorld, EventMeta, tool
from pinecall.client import Found
from pinecall.testing import Gateway
from pinecall.wire._names import JsonObject


class Clinica(Agent):
    """Eres la recepción."""

    stage: Literal["identify", "book"] = "identify"
    patient: str | None = None
    slot: str | None = None
    accepts = {"slot.released": ["app"]}  # noqa: RUF012 - the base's ClassVar
    view_template = "{% if patient %}Hablas con {{ patient }}.{% else %}Pide el nombre.{% endif %}"

    @override
    def on_call(self, call: CallWorld) -> None:
        """Know the caller by their number."""
        self.patient = None if call.from_ == "+34600000000" else "conocido"

    @override
    def on_event(self, name: str, data: JsonObject, meta: EventMeta) -> None:
        """Keep the slot released."""
        self.slot = str(data["at"])

    @tool(stage="identify")
    def find_patient(self, name: str) -> str:
        """Busca al paciente."""
        self.patient = name
        self.stage = "book"
        return name

    @tool(stage="book")
    async def hours(self, question: str) -> list[str]:
        """Busca en las bases."""
        return [one.text for one in await self.knowledge.search(question)]


def test_a_call_opens_with_its_prompt_and_its_tools_and_a_tool_moves_both() -> None:
    with Gateway() as pc:
        pc.mount(Clinica)
        call = pc.call_started()
        assert (call.prompt, call.tools, call.state["stage"]) == (
            "Pide el nombre.",
            ["find_patient"],
            "identify",
        )
        answered = call.tool("find_patient", name="Marta Ruiz")
        assert answered["output"] == "Marta Ruiz"
        assert (call.prompt, call.tools) == ("Hablas con Marta Ruiz.", ["hours"])
        assert pc.errors == []


def test_a_call_opened_in_a_state_and_one_handed_over_start_where_they_were() -> None:
    with Gateway() as pc:
        pc.mount(Clinica)
        assert pc.call_started(state={"patient": "Ana"}).prompt == "Hablas con Ana."
        assert pc.call_attached({"stage": "book", "patient": "Luis"}).prompt == "Hablas con Luis."


def test_an_outside_fact_and_a_search_reach_the_class_as_a_call_would_bring_them() -> None:
    with Gateway() as pc:
        pc.finds(Found("horario.md", None, "de 9 a 18"))
        pc.mount(Clinica)
        call = pc.call_started(state={"stage": "book"})
        call.fact("slot.released", {"at": "10:00"})
        assert call.state["slot"] == "10:00"
        assert call.tool("hours", question="¿a qué hora abren?")["output"] == ["de 9 a 18"]
        assert pc.searched == [(call.id, "¿a qué hora abren?", None)]


def test_the_callers_turn_and_the_end_are_entries_like_any_other() -> None:
    with Gateway() as pc:
        pc.mount(Clinica)
        call = pc.call_started()
        call.said("Hola, soy Ana.")
        call.ended()
        assert [one.type for one in call.commands][-1] in ("prompt.set", "tools.set", "state.set")
        assert pc.errors == []
