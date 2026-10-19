"""The framework's own words in a Studio agent's identity: word for word the SDKs' rules, protocols and channel."""

# The same text the TypeScript package's `built-in-rules.ts`, the Python SDK's `_rules.py` and the gem's
# `Rules` write: a Studio agent's prompt reads as a class's does.
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

ON_WHATSAPP = "You are on WhatsApp. Use its formatting: *bold*, _italic_, no headings, no tables, short messages."


def channel_rules_for(channel: str | None, medium: str | None) -> str:
    """How to write on this channel and medium: WhatsApp's formatting, a website's, or speech."""
    if channel == "whatsapp":
        return ON_WHATSAPP
    if channel == "web" and medium == "text":
        return ON_A_WEBSITE
    return SPOKEN


def tagged(name: str, text: str) -> str:
    """The text inside `<name>` … `</name>`; nothing for no text."""
    return f"<{name}>\n{text}\n</{name}>" if text.strip() else ""
