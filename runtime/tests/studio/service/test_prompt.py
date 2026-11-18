"""A Studio agent's identity: its instructions filled with the call's values, and the framework's words by channel."""

from runtime.studio.service import prompt
from runtime.wire.studio import ChannelRules
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


def test_an_agent_with_no_tool_is_told_it_has_none_and_never_to_call_one() -> None:
    """Saved with no tool and no data collection, it is not told to act by calling a tool, nor to hand over:
    what a call with no tool is told is the session's to say."""
    text = prompt.identity(clinic(tools=[], collect=None), {"call": {"channel": "phone", "medium": "voice"}})
    assert f"<protocols>\n{prompt.WITHOUT_TOOLS}\n</protocols>" in text
    assert "To act, call a tool" not in text and "hand over to a person" not in text


def test_an_agent_with_a_tool_or_data_collection_is_told_to_act_by_calling_it() -> None:
    """One HTTP tool, or data collection alone, is a tool the model acts with."""
    for acting in (clinic(collect=None), clinic(tools=[])):
        assert f"<protocols>\n{prompt.PROTOCOLS}\n</protocols>" in prompt.identity(acting, {})


def test_a_written_chat_on_a_website_is_told_markdown_is_fine() -> None:
    """The channel's rules follow the call: a website's text chat is not a phone call."""
    text = prompt.identity(clinic(), {"call": {"channel": "web", "medium": "text"}})
    assert "written chat on a website" in text and "phone call" not in text.split("<channel>")[1]


def test_a_spoken_call_of_an_agent_that_says_its_languages_is_told_to_answer_in_them() -> None:
    """One language is the one it answers in; several, the one the caller last spoke, and no other."""
    spoken = {"call": {"channel": "phone", "medium": "voice"}}
    assert "- The caller speaks Arabic: answer in Arabic." in prompt.identity(clinic(), spoken, ("ar",))
    several = prompt.identity(clinic(), spoken, ("hi", "en", "ta"))
    assert "- The caller speaks Hindi, English or Tamil: answer in the one they last spoke" in several
    assert "- Answer in the language the caller speaks." not in several
    unnamed = prompt.identity(clinic(), spoken, ("sw",))
    assert "- The caller speaks the language whose tag is sw: answer in the language whose tag is sw." in unnamed


def test_a_written_call_and_an_agent_that_says_no_language_keep_the_frameworks_rule() -> None:
    """A text has no ears or voice to keep to a language: it is answered in whatever it was written in."""
    written = {"call": {"channel": "whatsapp", "medium": "text"}}
    assert f"<rules>\n{prompt.RULES}\n</rules>" in prompt.identity(clinic(), written, ("ar", "en"))
    assert f"<rules>\n{prompt.RULES}\n</rules>" in prompt.identity(clinic(), {"call": {"medium": "voice"}})


def test_an_agent_that_writes_its_own_rules_for_a_channel_is_told_those_and_the_frameworks_on_the_others() -> None:
    """Its own WhatsApp words on WhatsApp; SMS, a website's chat and a call as the framework says them."""
    own = ChannelRules(whatsapp="You are on WhatsApp. One short message, no formatting at all.")
    agent = clinic(channel_rules=own)
    said = prompt.identity(agent, {"call": {"channel": "whatsapp", "medium": "text"}})
    assert "<channel>\nYou are on WhatsApp. One short message, no formatting at all.\n</channel>" in said
    assert prompt.ON_WHATSAPP not in said
    assert prompt.ON_SMS in prompt.identity(agent, {"call": {"channel": "sms", "medium": "text"}})
    assert prompt.SPOKEN in prompt.identity(agent, {"call": {"channel": "phone", "medium": "voice"}})
    assert prompt.list_channel_rules() == {
        "voice": prompt.SPOKEN,
        "chat": prompt.ON_A_WEBSITE,
        "whatsapp": prompt.ON_WHATSAPP,
        "sms": prompt.ON_SMS,
    }
