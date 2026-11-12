"""What a Studio agent declares, as an SDK would: its greeting, its tools, the fields it collects, its hang-up."""

from runtime.studio.service.declaring import declare, list_tool_specs
from tests.studio.factories import a_tool, clinic


def test_the_declaration_carries_the_greeting_the_tools_the_fields_and_the_hang_up() -> None:
    """What agent.configure sends: the HTTP tool, collect with every field optional, the fields as state."""
    declared = declare(clinic())
    assert declared.greeting is not None and declared.greeting.say == "Clínica Norte, buen día."
    tools = {tool.name: tool for tool in declared.tools or []}
    assert sorted(tools) == ["collect", "findPatient"]
    assert tools["findPatient"].parameters["required"] == ["phone"]
    assert tools["collect"].parameters["required"] == []
    assert [field.name for field in declared.state_fields or []] == ["name", "reason"]
    assert declared.hangup is not None


def test_a_parameters_values_reach_the_model_and_the_tools_lines_the_declaration() -> None:
    """`enum` is the schema's closed list; announce, delayed and failed travel on the spec with their moment."""
    talkative = a_tool(
        params=[{"name": "site", "enum": ["centro", "norte"]}],
        announce="One moment.",
        delayed="Still looking.",
        delayed_after_s=3,
        failed="The agenda is down.",
    )
    (spec,) = list_tool_specs(clinic(tools=[talkative], collect=None))
    assert spec.parameters["properties"]["site"] == {"type": "string", "enum": ["centro", "norte"]}
    assert (spec.announce, spec.delayed, spec.delayed_after_s, spec.failed) == (
        "One moment.",
        "Still looking.",
        3,
        "The agenda is down.",
    )


def test_the_declaration_sends_only_what_the_definition_sets() -> None:
    """No `record` or `uses_knowledge` by default: a default sent would fix a setting the console owns."""
    dumped = declare(clinic(collect=None, greeting=None)).model_dump(mode="json", exclude_unset=True, exclude_none=True)
    assert set(dumped) == {"tools", "state_fields"}


def test_an_agent_that_collects_nothing_has_no_collect_tool() -> None:
    """Instructions and tools alone."""
    assert [spec.name for spec in list_tool_specs(clinic(collect=None))] == ["findPatient"]
