# frozen_string_literal: true

# The shape of each command's data, as an app sends it.

module Pinecall
  module Wire
    module Shapes
      COMMANDS = {
        "AgentConfigure" => {
          config: { kind: :ref, ref: "AgentConfig", required: true }
        }.freeze,
        "AgentDrain" => {}.freeze,
        "AgentRegister" => {
          routes: { kind: :list, items: { kind: :ref, ref: "Route" }, required: true },
          sdk: { kind: :str },
          host: { kind: :str },
          takes_unclaimed: { kind: :bool, default: true },
          answers_dev: { kind: :bool, default: false }
        }.freeze,
        "AgentReply" => {
          instructions: { kind: :str, required: true },
          allow_interruptions: { kind: :bool }
        }.freeze,
        "AgentSay" => {
          text: { kind: :str, required: true },
          allow_interruptions: { kind: :bool }
        }.freeze,
        "CallAttention" => {
          reason: { kind: :str, required: true },
          wait_s: { kind: :float, required: true }
        }.freeze,
        "CallCallback" => {
          number: { kind: :str, required: true },
          when: { kind: :str },
          note: { kind: :str }
        }.freeze,
        "CallClaim" => {
          code: { kind: :str, required: true, pattern: "^[0-9]{4}$" }
        }.freeze,
        "CallDial" => {
          to: { kind: :str, required: true },
          from: { kind: :str },
          caller: { kind: :ref, ref: "Contact" },
          metadata: { kind: :json }
        }.freeze,
        "CallDtmf" => {
          digits: { kind: :str, required: true }
        }.freeze,
        "CallEvent" => {
          name: { kind: :str, required: true },
          data: { kind: :json, required: true }
        }.freeze,
        "CallHangup" => {
          reason: { kind: :str }
        }.freeze,
        "CallHold" => {}.freeze,
        "CallOptOut" => {
          note: { kind: :str, null: true }
        }.freeze,
        "CallLog" => {
          name: { kind: :str, required: true },
          data: { kind: :json, required: true }
        }.freeze,
        "CallMute" => {}.freeze,
        "CallTransfer" => {
          to: { kind: :str, required: true },
          mode: { kind: :ref, ref: "TransferMode" }
        }.freeze,
        "CallUnhold" => {}.freeze,
        "CallUnmute" => {}.freeze,
        "DevAnswer" => {
          id: { kind: :str, required: true },
          result: { kind: :json },
          refused: { kind: :ref, ref: "DevRefusal" }
        }.freeze,
        "ParticipantMute" => {
          identity: { kind: :str, required: true }
        }.freeze,
        "ParticipantRemove" => {
          identity: { kind: :str, required: true }
        }.freeze,
        "Ping" => {}.freeze,
        "PromptSet" => {
          name: { kind: :str, required: true },
          text: { kind: :str, required: true }
        }.freeze,
        "RoomInvite" => {
          to: { kind: :str, required: true },
          kind: { kind: :enum, values: %w[sip participant], required: true }
        }.freeze,
        "RoomSend" => {
          topic: { kind: :str, required: true },
          data: { kind: :json, required: true },
          to: { kind: :str }
        }.freeze,
        "SessionConfigure" => {
          state: { kind: :json },
          config: { kind: :ref, ref: "AgentConfig" }
        }.freeze,
        "StateSet" => {
          state: { kind: :json, required: true },
          changed: { kind: :list, items: { kind: :str } }
        }.freeze,
        "SupervisorVerb" => {
          by: { kind: :ref, ref: "Supervisor", required: true },
          verb: { kind: :ref, ref: "Verb", required: true }
        }.freeze,
        "ToolsSet" => {
          tools: { kind: :list, items: { kind: :ref, ref: "ToolSpec" }, required: true }
        }.freeze,
      }.freeze
    end
  end
end
