# frozen_string_literal: true

# What a class reaches its bases through: one verb, answered by the gateway for the call in hand.

module Pinecall
  class Agent
    # `knowledge.search("…", k: 3)` inside a tool: the bases attached to the agent, searched for
    # this call by the gateway, which logs what it found.
    class Knowledge
      def initialize(agent)
        @agent = agent
      end

      # The chunks found, each a `CallWorld::Found`.
      def search(query, k: nil) = @agent.call.search(query, k:)
    end
  end
end
