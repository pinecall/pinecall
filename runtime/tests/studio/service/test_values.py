"""What a Studio agent's placeholders read: the call as it started, the metadata it was opened with."""

from runtime.studio.service.prompt import fill
from runtime.studio.service.values import read_values
from runtime.wire.events import CallStarted


def test_a_metadata_placeholder_reads_what_the_call_was_opened_with_and_not_the_state_it_opened_in() -> None:
    """The token's `metadata` is `call.started.metadata`: what the exported class reads as `this.call.metadata`."""
    started = CallStarted.model_validate(
        {
            "channel": "web",
            "direction": "inbound",
            "from": "web_1",
            "to": "clinica-norte",
            "caller": {"name": "Ana"},
            "started_at": 1.0,
            "metadata": {"order": "A-17"},
            "state": {"order": "from a golden"},
        }
    )
    values = read_values(started)
    assert fill("Order {{metadata.order}} for {{caller.name}} on {{call.channel}}.", values) == (
        "Order A-17 for Ana on web."
    )
    assert read_values(started.model_copy(update={"metadata": None}))["metadata"] == {}
