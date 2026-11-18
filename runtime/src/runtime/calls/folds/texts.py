"""What a log says of its text messages: the SMS segments a conversation received and sent."""

from collections.abc import Iterable

from runtime.enums import Channel
from runtime.kit import sms
from runtime.wire.base import Entry

# Whose words each turn is: a contact's message comes as it was sent, an agent's goes out in parts.
_COUNTED = {"turn.user": sms.segments_of, "turn.agent": sms.segments_sent}


# A carrier bills both ways. Only what was durably written counts: an agent's turn the contact was
# sent is on the log, and one a stopped contact was not sent is counted too, which errs to the org's side
# by a segment at most.
def sms_segments(entries: Iterable[Entry]) -> int | None:
    """The segments an SMS conversation exchanged, both ways; None for a call on any other channel."""
    total, by_sms = 0, False
    for entry in entries:
        if entry.type == "call.started":
            by_sms = entry.data.get("channel") == Channel.sms.value
        text = entry.data.get("text")
        if entry.type in _COUNTED and not entry.ephemeral and isinstance(text, str):
            total += _COUNTED[entry.type](text)
    return total if by_sms else None
