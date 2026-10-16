# frozen_string_literal: true

module Pinecall
  # The framework's own words in the identity block: the rules, the protocols, and the channel's.
  # English for every agent: a model follows English instructions and answers in any language.
  # Constant within a call, so they stay in the cached prompt prefix. Word for word the TypeScript
  # package's `built-in-rules.ts`.
  module Rules
    RULES = [
      "- Invent nothing: if it did not come from a tool or from the knowledge, do not say it.",
      "- One question per turn, and wait for the answer.",
      "- Answer in the language the caller speaks."
    ].join("\n").freeze

    PROTOCOLS = [
      "- To act, call a tool; saying you have done something does not do it.",
      "- Before an irreversible action read back what you are about to do and wait for an explicit yes.",
      "- If you cannot solve it, say so and offer to hand over to a person."
    ].join("\n").freeze

    SPOKEN = "You are on a phone call. Everything you write is read aloud by a voice: short spoken sentences, " \
             "no lists, no bold, no symbols, no links. Say an email or a web address the way a person says it out loud."

    ON_A_WEBSITE = "You are in a written chat on a website. Markdown is fine: short paragraphs, a list when there " \
                   "are steps, bold for the one thing that matters."

    ON_WHATSAPP = "You are on WhatsApp. Use its formatting: *bold*, _italic_, no headings, no tables, short messages."

    module_function

    # How to write on this channel and medium: WhatsApp's formatting, a website's Markdown, or speech.
    def channel_rules_for(channel, medium)
      return ON_WHATSAPP if channel.to_s == "whatsapp"

      channel.to_s == "web" && medium.to_s == "text" ? ON_A_WEBSITE : SPOKEN
    end
  end
end
