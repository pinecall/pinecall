"""An SMS as a carrier counts it: the parts a long text goes out in, and the segments each is billed as."""

from runtime.kit.text import cut_in_parts

# What a carrier's API takes as one message (Twilio: 1,600 characters); a longer text goes out as several.
LONGEST = 1600
# GSM 03.38's alphabet: a text made of these alone is 7 bits a character. The second row counts two.
_GSM = frozenset(
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
)
_GSM_TWICE = frozenset("^{}\\[~]|€")
# One segment holds this many; a text of several loses the header that joins them.
_ALONE, _JOINED = (160, 153), (70, 67)


def parts_of(text: str) -> list[str]:
    """The text as the messages it goes out in, each within what a carrier takes, in order."""
    return cut_in_parts(text, LONGEST)


# A carrier bills a message by its segments: 160 characters of the GSM alphabet, or 70 of any
# other (one emoji or one accent outside it makes the whole message UCS-2), and 153 or 67 each once
# there are several.
def segments_of(message: str) -> int:
    """How many segments one message is billed as; none for an empty one."""
    if not message:
        return 0
    plain = all(sign in _GSM or sign in _GSM_TWICE for sign in message)
    if plain:
        length = sum(2 if sign in _GSM_TWICE else 1 for sign in message)
        alone, joined = _ALONE[0], _ALONE[1]
    else:
        length = len(message.encode("utf-16-le")) // 2
        alone, joined = _JOINED[0], _JOINED[1]
    return 1 if length <= alone else -(-length // joined)


def segments_sent(text: str) -> int:
    """How many segments a reply is billed as, cut in the parts it goes out in."""
    return sum(segments_of(part) for part in parts_of(text))
