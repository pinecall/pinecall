# frozen_string_literal: true

# The judges of {{Title}}'s own, as code: required by agent.rb into judges own:.

require "pinecall"

# A judge of the agent's own asks one question of every call at hang-up, answered held or broken; `pinecall judges try
# <name> --last 5` asks it of the last calls before you keep it. One looks like this:
#   MESSAGE_TAKEN = Pinecall.own_judge(name: "message-taken", asks: "Did the agent write the message down before saying goodbye?")
