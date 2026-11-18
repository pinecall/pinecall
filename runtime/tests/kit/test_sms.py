"""An SMS as a carrier counts it: its segments by alphabet, and the parts a long reply goes out in."""

import pytest

from runtime.kit import sms


@pytest.mark.parametrize(
    ("message", "segments"),
    [
        ("", 0),
        ("hola", 1),
        ("a" * 160, 1),
        ("a" * 161, 2),
        ("a" * 306, 2),
        ("a" * 307, 3),
        # One accent outside the GSM alphabet, or one emoji, makes the whole message UCS-2.
        ("ç" + "a" * 69, 1),
        ("ç" + "a" * 70, 2),
        ("qué tal, cómo estás", 1),
        ("ok 👍", 1),
        ("👍" * 36, 2),
        # The euro and the brackets are in the alphabet's extension: two characters each.
        ("€" * 80, 1),
        ("€" * 81, 2),
    ],
)
def test_a_message_is_billed_by_its_segments_in_the_alphabet_it_needs(message: str, segments: int) -> None:
    assert sms.segments_of(message) == segments


def test_a_reply_longer_than_a_carrier_takes_is_billed_part_by_part() -> None:
    """A reply of 2,000 characters goes out as two messages, each with its own segments."""
    reply = "palabra " * 250
    assert [len(part) <= sms.LONGEST for part in sms.parts_of(reply)] == [True, True]
    assert sms.segments_sent(reply) == sum(sms.segments_of(part) for part in sms.parts_of(reply))
    assert sms.segments_sent("hola") == 1
