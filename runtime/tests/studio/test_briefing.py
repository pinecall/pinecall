"""A Studio agent as a writer reads it before its first call: its instructions, how it opens, its tools."""

from pinecall_runtime.studio import service as studio
from tests.studio.test_definition import clinic


def test_the_brief_reads_the_instructions_the_greeting_and_every_tool() -> None:
    brief = studio.brief_of_definition(clinic())
    assert brief.prompt.startswith("You answer the phone for Clínica Norte.")
    assert "Opens the call with: Clínica Norte, buen día." in brief.prompt
    assert brief.tools[0] == "findPatient: Finds the patient by phone."
    # Data collection is a tool the model calls too: a writer knows what the agent asks for.
    assert brief.tools[1].startswith("collect: Saves what the caller told you")
    assert brief.knowledge == ""


def test_a_calls_values_are_not_in_the_brief() -> None:
    """`{{call.from}}` is a call's; with none, the placeholder is empty rather than shown as such."""
    brief = studio.brief_of_definition(clinic())
    assert "{{" not in brief.prompt
    assert "The caller dials from ." in brief.prompt


def test_an_agent_with_no_greeting_and_no_tools_is_its_instructions_alone() -> None:
    brief = studio.brief_of_definition(clinic(greeting=None, tools=[], collect=None))
    assert brief.prompt == "You answer the phone for Clínica Norte. The caller dials from ."
    assert brief.tools == ()
