# frozen_string_literal: true

# The state an empty log starts from, and the parts a fold writes into it.

module Pinecall
  module Wire
    # The state a log reduces to.
    module State
      module_function

      # The state of an empty log. Identical in all three languages, so one log reduces the same.
      def initial
        {
          seq: 0,
          agent: "",
          call: nil,
          status: "idle",
          channel: nil,
          direction: nil,
          from: nil,
          to: nil,
          caller: nil,
          room: nil,
          started_at: nil,
          ended_at: nil,
          end_reason: nil,
          outcome: nil,
          user_state: nil,
          agent_state: nil,
          live: { user: nil, agent: nil },
          turns: [],
          metrics: { llm: [], stt: [], tts: [], vad: [], eou: [], eot: [], interruption: [], realtime: [], avatar: [] },
          tools: [],
          app_state: {},
          events: [],
          prompt: {},
          tools_visible: [],
          confirms: [],
          memory: [],
          sources: [],
          handoff: { active: false, by: nil },
          held: false,
          muted: false,
          transfer: nil,
          attention: nil,
          usage: [],
          cost: nil,
          routes: [],
          gaps: [],
          errors: [],
          custom: []
        }
      end
    end
  end
end
