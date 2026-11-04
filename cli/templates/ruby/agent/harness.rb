# frozen_string_literal: true

# The judges and the callers of {{Title}}'s own, as code: required by agent.rb into judges own: and personas own:.

require "pinecall"

# Calls from the street, in a rush, with one thing to leave.
HURRIED = Pinecall.own_persona(
  name: "hurried",
  about: "Calls from the street, in a rush, with one thing to leave",
  goal: "leave a message for the business: I am Ana García and the delivery for tomorrow has to come after 4 pm",
  style: "short sentences, interrupts, gives one fact at a time, asks twice whether the message is written down",
  facts: { "their name" => "Ana García", "their phone" => "600 000 001" },
  expects: [
    "The agent should write the message down with the caller's name and what it is about.",
    "The agent should not promise when the business will call back."
  ],
  behavior: { interrupts: 0.3, pause_s: 1 }
)

# A judge of the agent's own asks one question of every call at hang-up, answered held or broken; `pinecall judges try
# <name> --last 5` asks it of the last calls before you keep it. One looks like this:
#   MESSAGE_TAKEN = Pinecall.own_judge(name: "message-taken", asks: "Did the agent write the message down before saying goodbye?")
