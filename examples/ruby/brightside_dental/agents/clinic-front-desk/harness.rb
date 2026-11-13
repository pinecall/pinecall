# frozen_string_literal: true

# The front desk's own judge and its two test callers.

require "pinecall"

# A judge asks one question of every call when it ends, and answers held or broken.
# `consent` and `grounded` are Pinecall's; this one is the clinic's own.
OFFERS_A_REAL_TIME = Pinecall.own_judge(
  name: "offers-a-real-time",
  asks: "Did every time the agent offered come from a free_slots result of this call?",
  reads: ["evidence"]
)

# A test caller: who they are, what they want and how they talk. `pinecall simulate` phones the
# agent as each one, and the judges read the call.
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
