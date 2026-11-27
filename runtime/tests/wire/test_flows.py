"""A flow's steps as an app's process sends them: what an extract step asks, read, and what it refuses."""

import pytest

from runtime.enums import StepKind
from runtime.exceptions import ValidationError
from runtime.wire.flows import ExtractStep, StepSent

A_NOTICE = {"type": "object", "properties": {"phone": {"type": "string"}, "name": {"type": "string"}}}


def test_an_extract_step_reads_the_agent_the_words_the_schema_and_what_to_look_for() -> None:
    asked = {"agent": "front-desk", "text": "Hay una consulta de Soledad, 11 3125 8777.", "schema": A_NOTICE}
    step = StepSent(seq=1, kind=StepKind.extract, asked={**asked, "instructions": "The person who asked."}).read()
    assert isinstance(step, ExtractStep)
    assert (step.agent, step.shape, step.instructions, step.model) == (
        "front-desk",
        A_NOTICE,
        "The person who asked.",
        None,
    )


@pytest.mark.parametrize(
    "schema",
    [{"type": "string"}, {"type": "object"}, {"type": "object", "properties": {}}],
    ids=["not an object", "no properties", "properties empty"],
)
def test_an_extract_step_whose_schema_is_no_object_with_properties_is_refused(schema: dict[str, object]) -> None:
    sent = StepSent(seq=1, kind=StepKind.extract, asked={"agent": "front-desk", "text": "Hola", "schema": schema})
    with pytest.raises(ValidationError, match="an extract step asks"):
        sent.read()


def test_an_extract_step_with_no_words_is_refused() -> None:
    sent = StepSent(seq=1, kind=StepKind.extract, asked={"agent": "front-desk", "text": "", "schema": A_NOTICE})
    with pytest.raises(ValidationError, match="an extract step asks"):
        sent.read()
