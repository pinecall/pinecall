"""The app's tools declared once as livekit's, the text the model reads of a result, and its read-back."""

from livekit.agents import RunContext, llm

from runtime.agents.declaration import Declaration, ToolSpec, Voicemail
from runtime.enums import Direction
from runtime.kit.text import Json
from runtime.session.call import Call, ToolUse
from runtime.session.lookups import RECALL
from runtime.session.tools import SAY_PARAMETER, VOICEMAIL_TOOL, as_livekit_tools, read_back, result_text
from runtime.wire.parts import ToolResult
from tests.conftest import needs_the_database
from tests.session.conftest import Box, a_session

BOOK = ToolSpec("book", "Book a table.", {"type": "object", "properties": {}}, timeout_s=0.1)


# ── what the model reads ──


def test_the_text_the_model_reads_is_the_error_then_the_summary_then_the_output() -> None:
    text = ToolResult(call_id="c", name="t", output={"a": 1}, summary="hecho", error="falló")
    assert result_text(text) == "falló"
    assert result_text(text.model_copy(update={"error": None})) == "hecho"
    assert result_text(ToolResult(call_id="c", name="t", output={"mesa": "4 ñ"})) == '{"mesa": "4 ñ"}'
    assert result_text(ToolResult(call_id="c", name="t", output="listo")) == "listo"
    assert result_text(ToolResult(call_id="c", name="t")) == ""


def test_a_list_output_travels_inside_an_object_or_anthropic_refuses_the_blocks() -> None:
    slots: list[Json] = [{"id": "s-1", "when": "el martes a las nueve"}]
    assert result_text(ToolResult(call_id="c", name="t", output=slots)) == (
        '{"items": [{"id": "s-1", "when": "el martes a las nueve"}]}'
    )


def test_a_confirm_is_rendered_from_the_call_and_the_result() -> None:
    result = ToolResult(call_id="c", name="book", output={"table": 4})
    text = read_back("Mesa {{result.table}} el {{slot.when}}", {"slot": {"when": "lunes"}}, result)
    assert text == "Mesa 4 el lunes"


def test_a_placeholder_nobody_filled_stays_visible_instead_of_vanishing() -> None:
    text = read_back("Hecho: {{result.code}}", {}, ToolResult(call_id="c", name="t", output={}))
    assert text == "Hecho: {{result.code}}"


# ── declared once ──


def test_every_declared_tool_becomes_a_raw_schema_tool_under_its_own_name() -> None:
    async def run(use: ToolUse, _context: RunContext[Call]) -> str:
        return use.name

    (tool,) = as_livekit_tools((BOOK,), run)
    assert isinstance(tool, llm.RawFunctionTool)
    assert tool.info.raw_schema == {
        "name": "book",
        "description": "Book a table.",
        "parameters": {"type": "object", "properties": {"say": SAY_PARAMETER}},
    }


def test_a_quiet_tool_is_offered_no_line_to_say() -> None:
    async def run(use: ToolUse, _context: RunContext[Call]) -> str:
        return use.name

    point = ToolSpec(
        "point", "Point at a thing.", {"type": "object", "properties": {"what": {"type": "string"}}}, quiet=True
    )
    (tool,) = as_livekit_tools((point,), run)
    assert isinstance(tool, llm.RawFunctionTool)
    assert set(tool.info.raw_schema["parameters"]["properties"]) == {"what"}


def test_the_line_to_say_is_asked_beside_the_tools_own_arguments_and_never_required() -> None:
    async def run(use: ToolUse, _context: RunContext[Call]) -> str:
        return use.name

    (tool,) = as_livekit_tools((RECALL,), run)
    assert isinstance(tool, llm.RawFunctionTool)
    parameters = tool.info.raw_schema["parameters"]
    assert set(parameters["properties"]) == {*RECALL.parameter_names, "say"}
    assert "say" not in parameters["required"]
    assert parameters["properties"]["say"]["type"] == "string"


def _names_offered(box: Box, declaration: Declaration, direction: Direction) -> list[str]:
    session = a_session(box, declaration, direction=direction)
    return [tool.id for tool in session.agent.tools if isinstance(tool, llm.Tool)]


@needs_the_database
async def test_voicemail_is_offered_on_a_call_the_agent_placed_and_only_when_it_is_set(box: Box) -> None:
    wanted = Declaration(slug="a", voicemail=Voicemail(message="Call us back"))
    assert _names_offered(box, wanted, Direction.outbound) == [VOICEMAIL_TOOL.name]
    assert _names_offered(box, wanted, Direction.inbound) == []
    assert _names_offered(box, Declaration(slug="a"), Direction.outbound) == []
