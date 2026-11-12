"""Data collection as the model reads it turn by turn: what is in, what is missing, and when to close."""

from runtime.studio.service.collect import is_complete, view
from runtime.wire.studio import Collect, Definition
from tests.studio.factories import clinic


def collected_by(definition: Definition) -> Collect:
    """What the definition collects."""
    assert definition.collect is not None
    return definition.collect


def test_the_view_says_what_is_in_what_is_missing_and_when_to_close() -> None:
    """Missing the name: asked for. With the name, the optional reason is still asked, and the call may close."""
    asking = view(collected_by(clinic()), {})
    assert "Still to collect" in asking and "name (string, required)" in asking
    assert "Every required field is in" not in asking
    closing = view(collected_by(clinic()), {"name": "Ana Ruiz"})
    assert '- name: "Ana Ruiz"' in closing
    assert "reason (string, optional)" in closing
    assert "Every required field is in" in closing
    assert is_complete(collected_by(clinic()), {"name": "Ana Ruiz"})


def test_a_field_with_a_closed_list_says_the_values_it_may_take() -> None:
    sized = collected_by(clinic(collect={"fields": [{"name": "size", "enum": ["S", "M"]}]}))
    assert "- size (string, required, one of: S, M)" in view(sized, {})
