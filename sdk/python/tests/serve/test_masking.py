"""What a served process prints: the values its agent declared private, masked as the log does."""

import pytest

from pinecall.serve._masking import Masking
from pinecall.wire._names import JsonObject
from pinecall.wire.frames import Entry
from pinecall.wire.parts import AgentConfig, StateFieldSpec, ToolSpec

DECLARED = AgentConfig(
    tools=[
        ToolSpec(
            name="takeMessage",
            description="Writes down who called.",
            parameters={"type": "object"},
            pii=["name"],
        )
    ],
    state_fields=[StateFieldSpec(name="patient", visibility="pii")],
)


def entry(type_: str, data: JsonObject) -> Entry:
    return Entry(seq=3, ts=1.0, call="CA_1", agent="desk", type=type_, ephemeral=False, data=data)


ASKED = entry(
    "tool.call",
    {
        "call_id": "tc_1",
        "name": "takeMessage",
        "arguments": {"name": "Ana Lopez", "about": "Ana Lopez wants a refund"},
    },
)


def test_a_tool_call_prints_the_argument_the_tool_names_and_the_value_another_repeats_masked() -> (
    None
):
    printed = Masking(DECLARED).entry(ASKED)
    assert printed.data["arguments"] == {"name": "***", "about": "*** wants a refund"}


def test_what_comes_after_the_tool_call_is_masked_of_its_value() -> None:
    masking = Masking(DECLARED)
    masking.entry(ASKED)
    state: JsonObject = {
        "state": {"message": {"name": "Ana Lopez"}, "stage": "done"},
        "changed": [],
    }
    result: JsonObject = {
        "call_id": "tc_1",
        "name": "takeMessage",
        "output": "Saved for Ana Lopez.",
    }
    line: JsonObject = {"name": "booked", "data": {"who": "Ana Lopez"}}
    assert masking.entry(entry("state.changed", state)).data["state"] == {
        "message": {"name": "***"},
        "stage": "done",
    }
    assert masking.entry(entry("tool.result", result)).data["output"] == "Saved for ***."
    assert masking.entry(entry("custom", line)).data["data"] == {"who": "***"}


def test_a_state_field_declared_private_is_masked_whole_before_any_tool_call() -> None:
    state: JsonObject = {"state": {"patient": {"id": 7}, "stage": "ask"}, "changed": ["patient"]}
    printed = Masking(DECLARED).entry(entry("state.changed", state))
    assert printed.data["state"] == {"patient": "***", "stage": "ask"}


def test_what_was_said_is_left_alone_and_an_agent_declaring_nothing_private_prints_as_is() -> None:
    masking = Masking(DECLARED)
    masking.entry(ASKED)
    said = entry("turn.user", {"speech_id": "s1", "text": "Soy Ana Lopez"})
    assert masking.entry(said) is said
    assert Masking(AgentConfig()).entry(ASKED) is ASKED


def test_a_value_is_masked_only_where_it_stands_as_a_whole_word() -> None:
    masking = Masking(DECLARED)
    masking.entry(
        entry("tool.call", {"call_id": "tc_9", "name": "takeMessage", "arguments": {"name": "Ana"}})
    )
    said = "Banana and Anabel, but Ana's, Ana, (Ana) and José Ana, Anaïs"
    printed = masking.entry(entry("custom", {"name": "x", "data": {"said": said}}))
    assert printed.data["data"] == {
        "said": "Banana and Anabel, but ***'s, ***, (***) and José ***, Anaïs"
    }


def test_a_value_shorter_than_three_characters_is_never_learned_and_one_of_three_is() -> None:
    short = Masking(DECLARED)
    for name in ("7", "ok", "Al", "  Bo ", ""):
        asked: JsonObject = {"call_id": "tc_9", "name": "takeMessage", "arguments": {"name": name}}
        short.entry(entry("tool.call", asked))
    line = entry("custom", {"name": "x", "data": {"who": "Al ok 7 Bo"}})
    assert short.entry(line) == line
    three = Masking(DECLARED)
    asked = {"call_id": "tc_9", "name": "takeMessage", "arguments": {"name": "Ann"}}
    three.entry(entry("tool.call", asked))
    assert three.entry(entry("custom", {"name": "x", "data": {"who": "Ann"}})).data["data"] == {
        "who": "***"
    }


@pytest.mark.parametrize("blank", ["", "   "])
def test_a_blank_argument_is_no_secret_because_it_would_mask_everything(blank: str) -> None:
    masking = Masking(DECLARED)
    masking.entry(
        entry("tool.call", {"call_id": "tc_2", "name": "takeMessage", "arguments": {"name": blank}})
    )
    line: JsonObject = {"name": "x", "data": {"who": "Ana"}}
    assert masking.entry(entry("custom", line)).data["data"] == {"who": "Ana"}
