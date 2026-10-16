"""`@tool`: what the model reads of a method, which ones this state shows, and running one."""

import asyncio
from typing import Literal

import pytest
from typing_extensions import override

from pinecall import Agent, DeclarationRefused, ToolFailed, tool
from pinecall._tools import run
from pinecall.wire.parts import ToolSpec


class Clinica(Agent):
    """Una clínica que da horas."""

    stage: Literal["identify", "book"] = "identify"
    patient: dict[str, str] | None = None

    @tool(stage="identify", pii=("name", "phone"))
    def find_patient(self, name: str, phone: str) -> dict[str, str]:
        """Busca al paciente por nombre y teléfono.

        Pide los dos antes de llamarla.
        """
        self.patient = {"name": name, "phone": phone}
        self.stage = "book"
        return self.patient

    @tool(stage="book", preview=2, announce="Voy a mirar la agenda.")
    async def free_slots(self, day: str, how_many: int = 3) -> list[str]:
        """Horas libres de un día."""
        return [f"{day} {10 + at}:00" for at in range(how_many)]

    @tool(stage="book", confirm="Le reservo el {{result}}. ¿Lo confirmo?", timeout=8)
    def book(self, chosen: str) -> str:
        """Reserva la hora que el paciente ya ha confirmado."""
        return chosen

    @tool
    def hours(self) -> str:
        """Dice el horario."""
        return "de 9 a 18"


@pytest.fixture
def clinica() -> Clinica:
    return Clinica().seal()


def spec_of(agent: Agent, name: str) -> ToolSpec:
    return next(spec for spec in agent.tools() if spec.name == name)


def test_the_docstring_is_what_the_model_reads_on_one_line(clinica: Clinica) -> None:
    assert spec_of(clinica, "find_patient").description == (
        "Busca al paciente por nombre y teléfono. Pide los dos antes de llamarla."
    )


def test_the_parameters_are_the_methods_own_with_their_types_and_defaults(clinica: Clinica) -> None:
    assert spec_of(clinica, "free_slots").parameters == {
        "type": "object",
        "properties": {
            "day": {"type": "string"},
            "how_many": {"type": "integer", "default": 3},
        },
        "required": ["day"],
        "additionalProperties": False,
    }


def test_an_announcement_travels_as_the_wire_carries_it(clinica: Clinica) -> None:
    assert spec_of(clinica, "free_slots").announce == "Voy a mirar la agenda."
    assert spec_of(clinica, "book").announce is None


def test_a_read_back_is_what_makes_a_tool_irreversible_on_the_wire(clinica: Clinica) -> None:
    book = spec_of(clinica, "book")
    assert (book.side_effect, book.timeout_s) == ("irreversible", 8.0)
    assert spec_of(clinica, "find_patient").side_effect == "read"


def test_a_declared_pii_parameter_travels_as_the_wire_carries_it(clinica: Clinica) -> None:
    assert spec_of(clinica, "find_patient").pii == ["name", "phone"]


def test_only_the_tools_this_state_shows_are_visible(clinica: Clinica) -> None:
    assert [spec.name for spec in clinica.visible_tools()] == ["find_patient", "hours"]
    clinica.run_tool("find_patient", {"name": "Ana", "phone": "600"})
    assert [spec.name for spec in clinica.visible_tools()] == ["free_slots", "book", "hours"]


def test_a_write_inside_a_tool_carries_the_tools_own_name(clinica: Clinica) -> None:
    clinica.run_tool("find_patient", {"name": "Ana", "phone": "600"})
    assert {change.author for change in clinica.changes()} == {"find_patient"}


def test_a_preview_cuts_what_the_model_sees_and_an_async_tool_runs_to_its_end(
    clinica: Clinica,
) -> None:
    assert clinica.run_tool("free_slots", {"day": "martes"}) == ["martes 10:00", "martes 11:00"]


def test_an_argument_is_converted_to_the_type_the_method_asked_for(clinica: Clinica) -> None:
    assert clinica.run_tool("free_slots", {"day": "martes", "how_many": "1"}) == ["martes 10:00"]


def test_what_the_model_sent_wrong_is_refused_before_the_method_runs(clinica: Clinica) -> None:
    with pytest.raises(ToolFailed, match="find_patient: phone is required; it takes no dni"):
        clinica.run_tool("find_patient", {"name": "Ana", "dni": "1"})
    with pytest.raises(ToolFailed, match="free_slots: how_many: Input should be a valid integer"):
        clinica.run_tool("free_slots", {"day": "martes", "how_many": "muchas"})
    assert clinica.changes() == []


def test_a_tool_the_agent_does_not_declare_is_refused_by_name(clinica: Clinica) -> None:
    with pytest.raises(ToolFailed, match="pay: this agent declares no such tool"):
        clinica.run_tool("pay")


def test_from_a_loop_an_async_tool_runs_on_it_and_a_def_on_a_thread_both_authored() -> None:
    async def both() -> tuple[object, object]:
        clinica = Clinica().seal()
        tools = getattr(Clinica, "_pinecall_tools")  # noqa: B009 - the class's own registry
        found = await run(clinica, tools["find_patient"], {"name": "Ana", "phone": "600"})
        slots = await run(clinica, tools["free_slots"], {"day": "lunes", "how_many": 1})
        assert {change.author for change in clinica.changes()} == {"find_patient"}
        return found, slots

    assert asyncio.run(both()) == ({"name": "Ana", "phone": "600"}, ["lunes 10:00"])


def test_a_subclass_keeps_its_parents_tools_and_an_override_without_tool_drops_one() -> None:
    class Callada(Clinica):
        """Una clínica que ya no da el horario."""

        @override
        def hours(self) -> str:
            return "no"

        @tool
        def hang_up(self) -> str:
            """Cuelga."""
            return "done"

    assert [spec.name for spec in Callada().tools()] == [
        "find_patient",
        "free_slots",
        "book",
        "hang_up",
    ]


def refused(body: dict[str, object]) -> str:
    with pytest.raises(DeclarationRefused) as error:
        type("Mala", (Agent,), {"__doc__": "Una clase mal declarada.", **body})
    return str(error.value)


def test_a_tool_with_no_docstring_is_refused_because_no_model_could_choose_it() -> None:
    def silent(self: Agent) -> None: ...

    assert "without a docstring no model can choose it" in refused({"silent": tool(silent)})


def test_a_tool_that_takes_more_than_a_model_can_name_is_refused_with_the_reason() -> None:
    def book(self: Agent, *chosen: str) -> None:
        """Reserva."""

    assert "a model fills a JSON object by name" in refused({"book": tool(book)})


def test_pii_naming_a_parameter_the_tool_does_not_have_is_refused() -> None:
    def find(self: Agent, name: str) -> None:
        """Busca."""

    assert "unknown: dni" in refused({"find": tool(pii=("dni",))(find)})


def test_a_stage_the_class_does_not_declare_is_refused_and_one_with_no_stage_says_what_to_add() -> (
    None
):
    def pay(self: Agent) -> None:
        """Paga."""

    staged = {"__annotations__": {"stage": Literal["identify", "book"]}, "stage": "identify"}
    assert "pay is not one of this agent's stages" in refused(
        {**staged, "pay": tool(stage="pay")(pay)}
    )
    assert "declares none; add stage: Literal" in refused({"pay": tool(stage="pay")(pay)})


def test_a_tool_named_like_the_agents_own_method_is_refused() -> None:
    def log(self: Agent) -> None:
        """Anota."""

    assert "would hide the agent's own log" in refused({"log": tool(log)})


def test_an_option_tool_does_not_take_is_refused_by_name() -> None:
    with pytest.raises(DeclarationRefused, match="@tool takes no retries"):
        tool(retries=3)  # pyright: ignore[reportCallIssue]
