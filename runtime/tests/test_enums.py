"""What a channel says of a call on it: whether somebody is on the line."""

import pytest

from runtime.enums import Channel


@pytest.mark.parametrize(
    ("channel", "on_the_line"), [("phone", True), ("web", True), ("whatsapp", False), ("sms", False), ("email", False)]
)
def test_a_call_is_live_while_somebody_is_on_it_and_a_written_conversation_never_is(
    channel: str, on_the_line: bool
) -> None:
    """A WhatsApp, SMS or email conversation is open for hours between two messages: open, never live."""
    assert Channel(channel).is_live(sealed=False) is on_the_line
    assert not Channel(channel).is_live(sealed=True)
