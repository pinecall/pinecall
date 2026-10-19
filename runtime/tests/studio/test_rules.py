"""The framework's words a Studio agent's identity carries, by channel, as the SDKs write them."""

from pinecall_runtime.studio.service import rules


def test_each_channel_is_told_how_to_write() -> None:
    """WhatsApp its formatting, a website's text chat Markdown, every voice call speech."""
    assert rules.channel_rules_for("whatsapp", "text") == rules.ON_WHATSAPP
    assert rules.channel_rules_for("web", "text") == rules.ON_A_WEBSITE
    assert rules.channel_rules_for("web", "voice") == rules.SPOKEN
    assert rules.channel_rules_for("phone", None) == rules.SPOKEN


def test_a_tag_around_nothing_is_nothing() -> None:
    """An empty block adds no empty tags to the prompt."""
    assert rules.tagged("tools", "") == ""
    assert rules.tagged("rules", "- one") == "<rules>\n- one\n</rules>"
