"""The framework's words in identity: English rules for every agent, and the channel's block."""

import re

import pytest

from pinecall import Agent, Line, render
from pinecall._rules import ON_A_WEBSITE, ON_WHATSAPP, SPOKEN, medium_of
from pinecall.wire._names import Channel, Medium


class Clinica(Agent):
    """Agenda de la Clínica Norte."""


class SinCanal(Agent):
    """Agenda que escribe sus propias normas de formato."""

    channel_rules = False


def identity_of(agent: Agent, line: Line | None = None) -> str:
    return render(agent, line)["identity"]


def tag_of(name: str, identity: str) -> str:
    found = re.search(rf"<{name}>\n(.*?)\n</{name}>", identity, re.DOTALL)
    assert found is not None
    return found[1]


def test_the_rules_are_english_for_every_agent_and_tell_it_to_answer_in_the_callers_language() -> (
    None
):
    identity = identity_of(Clinica())
    assert "One question per turn" in identity
    assert "- Answer in the language the caller speaks." in identity
    assert "To act, call a tool" in identity


def test_how_to_write_is_the_channels_block_not_a_rule() -> None:
    rules = tag_of("rules", identity_of(Clinica()))
    assert "markdown" not in rules.lower()
    assert "phone" not in rules


@pytest.mark.parametrize(
    ("channel", "medium", "said"),
    [
        ("phone", "voice", SPOKEN),
        ("web", "voice", SPOKEN),
        ("web", "text", ON_A_WEBSITE),
        ("whatsapp", "text", ON_WHATSAPP),
        ("whatsapp", "voice", ON_WHATSAPP),
        ("phone", None, SPOKEN),
        ("web", None, SPOKEN),
        ("whatsapp", None, ON_WHATSAPP),
    ],
)
def test_each_channel_and_medium_says_how_to_write_there(
    channel: Channel, medium: Medium | None, said: str
) -> None:
    assert tag_of("channel", identity_of(Clinica(), Line(channel, medium))) == said


def test_with_no_call_at_all_it_is_a_phone_calls() -> None:
    assert tag_of("channel", identity_of(Clinica())) == SPOKEN


def test_a_call_whose_gateway_does_not_say_takes_the_medium_its_channel_implies() -> None:
    assert [medium_of("phone", None), medium_of("web", None), medium_of("whatsapp", None)] == [
        "voice",
        "voice",
        "text",
    ]
    assert medium_of("whatsapp", "voice") == "voice"


def test_the_texts_are_the_ones_the_framework_ships_word_for_word() -> None:
    assert SPOKEN == (
        "You are on a phone call. Everything you write is read aloud by a voice: short spoken "
        "sentences, no lists, no bold, no symbols, no links. Say an email or a web address the "
        "way a person says it out loud."
    )
    assert ON_A_WEBSITE == (
        "You are in a written chat on a website. Markdown is fine: short paragraphs, a list when "
        "there are steps, bold for the one thing that matters."
    )
    assert ON_WHATSAPP == (
        "You are on WhatsApp. Use its formatting: *bold*, _italic_, no headings, no tables, "
        "short messages."
    )


@pytest.mark.parametrize("channel", ["phone", "web", "whatsapp"])
def test_a_class_with_channel_rules_false_leaves_the_block_out_on_every_channel(
    channel: Channel,
) -> None:
    identity = identity_of(SinCanal(), Line(channel))
    assert "<channel>" not in identity
    assert "<protocols>" in identity
