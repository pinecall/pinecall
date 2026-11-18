"""A Studio agent's prompt: its instructions with a call's values in them, and the framework's own words."""

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any, cast

from runtime.kit.languages import name_language
from runtime.studio.service.definition import A_PLACEHOLDER
from runtime.wire.parts import ToolSpec
from runtime.wire.studio import ChannelRules, Definition

# The same text the TypeScript package's `built-in-rules.ts`, the Python SDK's `_rules.py` and the gem's
# `Rules` write: a Studio agent's prompt reads as a class's does.
INVENT_NOTHING = "- Invent nothing: if it did not come from a tool or from the knowledge, do not say it."
ONE_QUESTION = "- One question per turn, and wait for the answer."
IN_THEIR_LANGUAGE = "- Answer in the language the caller speaks."
# A spoken call of an agent that says its languages is heard and spoken in those alone: a reply in any
# other is read by a voice that does not speak it. A class says this in its own words; Studio's prompt
# is the framework's, so it says it here.
IN_THE_ONE = "- The caller speaks {language}: answer in {language}."
# A small model keeps to the language a call began in: told only to answer "in the one they last spoke",
# it answered a caller who had changed to English in Spanish (production, 2026-11-18).
IN_ONE_OF_THEM = (
    "- The caller speaks {languages} and may change from one to the other at any moment: write each reply "
    "whole in the language of the caller's last message, whatever language the call was in before it, and "
    "never in any other language."
)
RULES = "\n".join((INVENT_NOTHING, ONE_QUESTION, IN_THEIR_LANGUAGE))

PROTOCOLS = (
    "- To act, call a tool in the same reply; saying you have done something, or that you are"
    " about to, does not do it. Never ask the caller to wait: once you stop talking, nothing"
    " happens until they speak again.\n"
    "- Before an irreversible action read back what you are about to do"
    " and wait for an explicit yes.\n"
    "- If you cannot solve it, say so and offer to hand over to a person."
)

# An agent saved with no tool and no data collection is not told to act by calling a tool, nor to
# offer a person it cannot hand over to: what it is told instead is the session's to say, on every
# request that has no tool (session/prompt.py, NO_TOOLS), whoever wrote the agent.
WITHOUT_TOOLS = "- Never ask the caller to wait: once you stop talking, nothing happens until they speak again."

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
ON_SMS = (
    "You are answering by SMS. Plain text only: no markdown, no lists, no emoji unless the person uses"
    " them. One short message, a few sentences at most."
)


def rules_for(languages: Sequence[str], medium: str | None) -> str:
    """The framework's rules, the last one naming the languages of a spoken call whose agent says them."""
    named = [name_language(one) for one in languages]
    if medium == "text" or not named:
        return RULES
    if len(named) == 1:
        return "\n".join((INVENT_NOTHING, ONE_QUESTION, IN_THE_ONE.format(language=named[0])))
    several = f"{', '.join(named[:-1])} or {named[-1]}"
    return "\n".join((INVENT_NOTHING, ONE_QUESTION, IN_ONE_OF_THEM.format(languages=several)))


def channel_rules_for(channel: str | None, medium: str | None, own: ChannelRules | None = None) -> str:
    """How to write on this channel and medium: the agent's own words for it, else the framework's."""
    if channel == "whatsapp":
        return (own and own.whatsapp) or ON_WHATSAPP
    if channel == "sms":
        return (own and own.sms) or ON_SMS
    if channel == "web" and medium == "text":
        return (own and own.chat) or ON_A_WEBSITE
    return (own and own.voice) or SPOKEN


# What the console shows under each channel before an agent writes its own.
def list_channel_rules() -> dict[str, str]:
    """The framework's own rules, by the name a definition writes its own under."""
    return {"voice": SPOKEN, "chat": ON_A_WEBSITE, "whatsapp": ON_WHATSAPP, "sms": ON_SMS}


def protocols_for(definition: Definition) -> str:
    """How the agent acts: by calling the tools it has, or, with none, by saying it cannot."""
    return PROTOCOLS if definition.tools or definition.collect is not None else WITHOUT_TOOLS


def tag(name: str, text: str) -> str:
    """The text inside `<name>` … `</name>`; nothing for no text."""
    return f"<{name}>\n{text}\n</{name}>" if text.strip() else ""


def fill(text: str, values: Mapping[str, Any]) -> str:
    """The text with each `{{a.b}}` filled from the values; one that names nothing is left empty."""

    def read(found: re.Match[str]) -> str:
        value: object = values
        for part in found.group(1).split("."):
            value = cast("Mapping[str, object]", value).get(part) if isinstance(value, Mapping) else None
            if value is None:
                return ""
        return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)

    return A_PLACEHOLDER.sub(read, text)


# The call's values and its languages are known when it starts and never change, so the block stays in
# the cached prefix.
def identity(definition: Definition, values: Mapping[str, Any], languages: Sequence[str] = ()) -> str:
    """The instructions, the call's values in their placeholders, then the framework's rules and the channel's."""
    call: Mapping[str, Any] = values.get("call") or {}
    medium = call.get("medium")
    said = [
        fill(definition.instructions, values),
        tag("rules", rules_for(languages, medium)),
        tag("protocols", protocols_for(definition)),
        tag("channel", channel_rules_for(call.get("channel"), medium, definition.channel_rules)),
    ]
    return "\n\n".join(part for part in said if part.strip())


def tools_block(specs: Sequence[ToolSpec]) -> str:
    """The `tools` block: each tool on a line, its name and what it does, as an SDK writes it."""
    return tag("tools", "\n".join(f"- {spec.name}: {spec.description}" for spec in specs))
