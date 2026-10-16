"""The framework's own words in the identity block: the rules, the protocols, and the channel's."""

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
    "- To act, call a tool; saying you have done something does not do it.\n"
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


def medium_of(channel: Channel, medium: Medium | None) -> Medium:
    """The medium a call is had in: the one the gateway said, else the one its channel implies."""
    if medium is not None:
        return medium
    return "text" if channel == "whatsapp" else "voice"


def channel_rules_for(channel: Channel, medium: Medium | None) -> str:
    """How to write on this channel and medium: WhatsApp's formatting, a website's, or speech."""
    if channel == "whatsapp":
        return ON_WHATSAPP
    if channel == "web" and medium_of(channel, medium) == "text":
        return ON_A_WEBSITE
    return SPOKEN
