/** The framework's own words in the identity block: the rules, the protocols, and the channel's. */

import { type Medium } from "../wire/defs.js";

// English for every agent: a model follows English instructions and answers in any language.
// Constant within a call, so they stay in the cached prompt prefix.

/** The rules every agent is given. */
export const RULES = [
  "- Invent nothing: if it did not come from a tool or from the knowledge, do not say it.",
  "- One question per turn, and wait for the answer.",
  "- Answer in the language the caller speaks.",
].join("\n");

/** The protocols every agent is given. */
export const PROTOCOLS = [
  "- To act, call a tool in the same reply; saying you have done something, or that you are about to, " +
    "does not do it. Never ask the caller to wait: once you stop talking, nothing happens until they speak again.",
  "- Before an irreversible action read back what you are about to do and wait for an explicit yes.",
  "- If you cannot solve it, say so and offer to hand over to a person.",
].join("\n");

const SPOKEN =
  "You are on a phone call. Everything you write is read aloud by a voice: short spoken sentences, " +
  "no lists, no bold, no symbols, no links. Say an email or a web address the way a person says it out loud.";

const ON_A_WEBSITE =
  "You are in a written chat on a website. Markdown is fine: short paragraphs, a list when there " +
  "are steps, bold for the one thing that matters.";

const ON_WHATSAPP = "You are on WhatsApp. Use its formatting: *bold*, _italic_, no headings, no tables, short messages.";

const ON_SMS =
  "You are answering by SMS. Plain text only: no markdown, no lists, no emoji unless the person uses them. " +
  "One short message, a few sentences at most.";

const ON_EMAIL =
  "You are answering an email. Write the whole reply in one message: a greeting with the person's name when you know it, " +
  "short paragraphs, a list with - when you give steps or options, **bold** for what they must not miss, links written out. " +
  "Answer everything they asked. Close with a one-line sign-off. No subject line: it is set for you.";

/** The channels an agent may write its own rules for: a spoken call, a website's written chat, WhatsApp, SMS, email. */
export type ChannelName = "voice" | "chat" | "whatsapp" | "sms" | "email";

/** An agent's own words for the channels it names, in place of the framework's; a channel left out keeps the framework's. */
export type ChannelRules = Partial<Record<ChannelName, string>>;

/** The framework's own rules, by the name an agent writes its own under. */
export const CHANNEL_RULES: Readonly<Record<ChannelName, string>> = { voice: SPOKEN, chat: ON_A_WEBSITE, whatsapp: ON_WHATSAPP, sms: ON_SMS, email: ON_EMAIL };

function channelNameOf(channel: string | undefined, medium: Medium): ChannelName {
  if (channel === "whatsapp" || channel === "sms" || channel === "email") return channel;
  return channel === "web" && medium === "text" ? "chat" : "voice";
}

/** How to write on this channel and medium: the agent's own words for it, else WhatsApp's formatting, a website's Markdown, or speech. */
export function channelRulesFor(channel: string | undefined, medium: Medium, own: ChannelRules = {}): string {
  const name = channelNameOf(channel, medium);
  return own[name] ?? CHANNEL_RULES[name];
}
