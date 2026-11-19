# frozen_string_literal: true

# The callers the front desk is tested with: `pinecall simulate` phones the agent as each one.

require "pinecall"

# A test caller: who they are, what they want and how they talk. Every `Pinecall.own_persona` here is
# the front desk's own, and the judges read each call. `ON = %w[in-a-hurry]` would add Pinecall's.
HURRIED = Pinecall.own_persona(
  name: "hurried",
  goal: "I want a cleaning this Thursday morning, the earliest time you have",
  style: "short sentences, interrupts, gives my name only when asked",
  expects: ["The agent should offer times from the agenda and book the one I choose."]
)

CHARGED_TWICE = Pinecall.own_persona(
  name: "charged-twice",
  goal: "I was charged twice for last month's cleaning and I want one charge back",
  style: "polite, a little annoyed, has the invoice number at hand",
  expects: ["The agent should pass me to billing, and never promise a refund itself."]
)
