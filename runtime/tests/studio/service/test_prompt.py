"""A Studio agent's identity: its instructions filled with the call's values, and the framework's words by channel."""

from runtime.studio.service import prompt
from tests.studio.factories import clinic


def test_each_channel_is_told_how_to_write() -> None:
    """WhatsApp its formatting, a website's text chat Markdown, every voice call speech."""
    assert prompt.channel_rules_for("whatsapp", "text") == prompt.ON_WHATSAPP
    assert prompt.channel_rules_for("web", "text") == prompt.ON_A_WEBSITE
    assert prompt.channel_rules_for("web", "voice") == prompt.SPOKEN
    assert prompt.channel_rules_for("phone", None) == prompt.SPOKEN


def test_a_tag_around_nothing_is_nothing() -> None:
    """An empty block adds no empty tags to the prompt."""
    assert prompt.tag("tools", "") == ""
    assert prompt.tag("rules", "- one") == "<rules>\n- one\n</rules>"


def test_the_identity_fills_the_calls_values_and_leaves_an_unknown_one_empty() -> None:
    """`{{call.from}}` is the caller; `{{metadata.nothing}}` is nothing at all."""
    text = prompt.identity(clinic(), {"call": {"from": "+59899123456", "channel": "phone", "medium": "voice"}})
    assert text.startswith("You answer the phone for Clínica Norte. The caller dials from +59899123456.\n\n<rules>")
    assert "<protocols>" in text and "You are on a phone call." in text
    assert prompt.fill("a{{metadata.nothing}}b", {"metadata": {}}) == "ab"


def test_a_written_chat_on_a_website_is_told_markdown_is_fine() -> None:
    """The channel's rules follow the call: a website's text chat is not a phone call."""
    text = prompt.identity(clinic(), {"call": {"channel": "web", "medium": "text"}})
    assert "written chat on a website" in text and "phone call" not in text.split("<channel>")[1]
