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
      "- To act, call a tool in the same reply; saying you have done something, or that you are about to, " \
      "does not do it. Never ask the caller to wait: once you stop talking, nothing happens until they speak again.",
      "- Before an irreversible action read back what you are about to do and wait for an explicit yes.",
      "- If you cannot solve it, say so and offer to hand over to a person."
    ].join("\n").freeze

    SPOKEN = "You are on a phone call. Everything you write is read aloud by a voice: short spoken sentences, " \
             "no lists, no bold, no symbols, no links. Say an email or a web address the way a person says it out loud."

    ON_A_WEBSITE = "You are in a written chat on a website. Markdown is fine: short paragraphs, a list when there " \
                   "are steps, bold for the one thing that matters."

    ON_WHATSAPP = "You are on WhatsApp. Use its formatting: *bold*, _italic_, no headings, no tables, short messages."

    ON_SMS = "You are answering by SMS. Plain text only: no markdown, no lists, no emoji unless the person uses " \
             "them. One short message, a few sentences at most."

    ON_EMAIL = "You are answering an email. Write the whole reply in one message: a greeting with the person's " \
               "name when you know it, short paragraphs, a list with - when you give steps or options, **bold** " \
               "for what they must not miss, links written out. Answer everything they asked. Close with a " \
               "one-line sign-off. No subject line: it is set for you."

    ON_MESSENGER = "You are on Facebook Messenger. Short plain messages: no Markdown, no headings, no tables; " \
                   "a link written out whole."

    ON_INSTAGRAM = "You are in Instagram's direct messages. Short plain messages, one idea each: no Markdown, no " \
                   "headings, no tables; a link written out whole, and few of them."

    # The channels a contact writes on message by message.
    WRITTEN = %w[whatsapp sms email messenger instagram].freeze

    # The framework's own rules, by the name an agent writes its own under: a spoken call, a website's
    # written chat, WhatsApp, SMS, email, Messenger, Instagram.
    CHANNEL_RULES = { voice: SPOKEN, chat: ON_A_WEBSITE, whatsapp: ON_WHATSAPP, sms: ON_SMS, email: ON_EMAIL,
                      messenger: ON_MESSENGER, instagram: ON_INSTAGRAM }.freeze

    module_function

    # The name a channel's rules are written under: `whatsapp`, `sms`, `email`, a website's `chat`, else `voice`.
    def channel_name_of(channel, medium)
      return channel.to_sym if WRITTEN.include?(channel.to_s)

      channel.to_s == "web" && medium.to_s == "text" ? :chat : :voice
    end

    # How to write on this channel and medium: the agent's own words for it, else WhatsApp's formatting,
    # a website's Markdown, or speech.
    def channel_rules_for(channel, medium, own = {})
      name = channel_name_of(channel, medium)
      own.transform_keys(&:to_sym).fetch(name, CHANNEL_RULES.fetch(name))
    end
  end
end
