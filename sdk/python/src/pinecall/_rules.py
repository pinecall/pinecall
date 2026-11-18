"""The framework's own words in the identity block: the rules, the protocols, and the channel's."""

from collections.abc import Mapping

from pinecall.wire._names import Channel, Medium

# English for every agent: a model follows English instructions and answers in any language.
# Constant within a call, so they stay in the cached prefix. Word for word the TypeScript
# package's `built-in-rules.ts` and the gem's `Rules`.
RULES = (
    "- Invent nothing: if it did not come from a tool or from the knowledge, do not say it.\n"
    "- One question per turn, and wait for the answer.\n"
    "- Answer in the language the caller speaks."
)

PROTOCOLS = (
    "- To act, call a tool in the same reply; saying you have done something, or that you are"
    " about to, does not do it. Never ask the caller to wait: once you stop talking, nothing"
    " happens until they speak again.\n"
    "- Before an irreversible action read back what you are about to do"
    " and wait for an explicit yes.\n"
    "- If you cannot solve it, say so and offer to hand over to a person."
)

SPOKEN = (
    "You are on a phone call. Everything you write is read aloud by a voice: short spoken"
    " sentences, no lists, no bold, no symbols, no links. Say an email or a web address the way"
    " a person says it out loud."
)

ON_A_WEBSITE = (
    "You are in a written chat on a website. Markdown is fine: short paragraphs, a list when"
    " there are steps, bold for the one thing that matters."
)

ON_WHATSAPP = (
    "You are on WhatsApp. Use its formatting: *bold*, _italic_, no headings, no tables,"
    " short messages."
)

ON_SMS = (
    "You are answering by SMS. Plain text only: no markdown, no lists, no emoji unless the person"
    " uses them. One short message, a few sentences at most."
)
ON_EMAIL = (
    "You are answering an email. Write the whole reply in one message: a greeting with the"
    " person's name when you know it, short paragraphs, a list with - when you give steps or"
    " options, **bold** for what they must not miss, links written out. Answer everything they"
    " asked. Close with a one-line sign-off. No subject line: it is set for you."
)


def medium_of(channel: Channel, medium: Medium | None) -> Medium:
    """The medium a call is had in: the one the gateway said, else the one its channel implies."""
    if medium is not None:
        return medium
    return "text" if channel in ("whatsapp", "sms", "email") else "voice"


# The framework's own rules, by the name an agent writes its own under: a spoken call, a website's
# written chat, WhatsApp, SMS, email.
CHANNEL_RULES: Mapping[str, str] = {
    "voice": SPOKEN,
    "chat": ON_A_WEBSITE,
    "whatsapp": ON_WHATSAPP,
    "sms": ON_SMS,
    "email": ON_EMAIL,
}


def channel_name_of(channel: Channel, medium: Medium | None) -> str:
    """The name a channel's rules are written under: a written channel's, `chat`, else `voice`."""
    if channel in ("whatsapp", "sms", "email"):
        return channel
    return "chat" if channel == "web" and medium_of(channel, medium) == "text" else "voice"


def channel_rules_for(
    channel: Channel, medium: Medium | None, own: Mapping[str, str] | None = None
) -> str:
    """How to write on this channel and medium: the agent's own words, else the framework's."""
    name = channel_name_of(channel, medium)
    return (own or {}).get(name, CHANNEL_RULES[name])
