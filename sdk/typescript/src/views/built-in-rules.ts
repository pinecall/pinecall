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
  "- To act, call a tool; saying you have done something does not do it.",
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

/** How to write on this channel and medium: WhatsApp's formatting, a website's Markdown, or speech. */
export function channelRulesFor(channel: string | undefined, medium: Medium): string {
  if (channel === "whatsapp") return ON_WHATSAPP;
  return channel === "web" && medium === "text" ? ON_A_WEBSITE : SPOKEN;
}
