"""What a log says of its text messages: the SMS segments a conversation exchanged."""

from runtime.calls import folds
from tests.calls.factories import entry


def test_an_sms_conversation_counts_the_segments_it_received_and_sent() -> None:
    """Both ways, as a carrier bills them: a long reply by its parts, an accent by the alphabet it forces."""
    log = [
        entry(1, "call.started", {"channel": "sms", "direction": "inbound", "from": "+1555", "to": "+1666"}),
        entry(2, "turn.user", {"text": "hola"}),
        entry(3, "turn.agent", {"text": "a" * 200}),
        entry(4, "turn.user", {"text": "qué bueno, gracias"}),
        entry(5, "turn.agent", {"text": "de nada"}),
    ]
    assert folds.sms_segments(log) == 1 + 2 + 1 + 1


def test_a_call_on_any_other_channel_exchanged_no_sms() -> None:
    for channel in ("phone", "web", "whatsapp"):
        log = [entry(1, "call.started", {"channel": channel}), entry(2, "turn.agent", {"text": "hola"})]
        assert folds.sms_segments(log) is None
