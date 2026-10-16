# frozen_string_literal: true

# The shapes the events, commands and doors are made of.

module Pinecall
  module Wire
    module Shapes
      PARTS = {
        "Contact" => {
          id: { kind: :str },
          phone: { kind: :str },
          name: { kind: :str },
          email: { kind: :str },
          external_id: { kind: :str }
        }.freeze,
        "Route" => {
          channel: { kind: :ref, ref: "Channel", required: true },
          number: { kind: :str, null: true, required: true },
          label: { kind: :str }
        }.freeze,
        "Supervisor" => {
          id: { kind: :str, required: true },
          name: { kind: :str }
        }.freeze,
        "MemoryFact" => {
          id: { kind: :str },
          text: { kind: :str, required: true },
          category: { kind: :str },
          score: { kind: :float },
          source: { kind: :str }
        }.freeze,
        "MemoryOp" => {
          op: { kind: :enum, values: %w[recall remember forget], required: true },
          contact: { kind: :str },
          query: { kind: :str },
          facts: { kind: :list, items: { kind: :ref, ref: "MemoryFact" }, required: true },
          took_ms: { kind: :float, required: true }
        }.freeze,
        "DocSource" => {
          id: { kind: :str, required: true },
          base: { kind: :str },
          path: { kind: :str, required: true },
          heading: { kind: :str },
          score: { kind: :float, required: true },
          excerpt: { kind: :str }
        }.freeze,
        "CostRow" => {
          provider: { kind: :str, required: true },
          model: { kind: :str, required: true },
          unit: { kind: :enum, values: %w[input_tokens cached_input_tokens cache_creation_tokens output_tokens characters audio_seconds requests session_seconds minutes], required: true },
          quantity: { kind: :float, required: true },
          unit_price_usd: { kind: :float, required: true },
          usd: { kind: :float, required: true }
        }.freeze,
        "UnpricedRow" => {
          provider: { kind: :str, required: true },
          model: { kind: :str, required: true }
        }.freeze,
        "Cost" => {
          usd: { kind: :float, required: true },
          rows: { kind: :list, items: { kind: :ref, ref: "CostRow" }, required: true },
          unpriced: { kind: :list, items: { kind: :ref, ref: "UnpricedRow" }, required: true }
        }.freeze,
        "Entry" => {
          seq: { kind: :int, required: true },
          ts: { kind: :float, required: true },
          call: { kind: :str, null: true, required: true },
          agent: { kind: :str, required: true },
          type: { kind: :str, required: true },
          ephemeral: { kind: :bool, required: true },
          data: { kind: :json, required: true }
        }.freeze,
        "Command" => {
          type: { kind: :str, required: true },
          agent: { kind: :str, required: true },
          call: { kind: :str, null: true, required: true },
          id: { kind: :str },
          data: { kind: :json, required: true }
        }.freeze,
        "Metadata" => {
          model_name: { kind: :str, null: true },
          model_provider: { kind: :str, null: true }
        }.freeze,
        "TurnMetadata" => {
          model_name: { kind: :str },
          model_provider: { kind: :str }
        }.freeze,
        "GoldenQuestion" => {
          asks: { kind: :str, required: true },
          expects: { kind: :str, required: true }
        }.freeze,
        "GoldenMiss" => {
          asks: { kind: :str, required: true },
          expects: { kind: :str, required: true },
          found: { kind: :list, items: { kind: :str }, required: true }
        }.freeze,
        "KnowledgeBase" => {
          base: { kind: :str, required: true },
          chunks: { kind: :int, required: true },
          model: { kind: :str, required: true },
          pushed_at: { kind: :float, required: true }
        }.freeze,
        "ContactFact" => {
          id: { kind: :str },
          text: { kind: :str, required: true },
          category: { kind: :str },
          source: { kind: :str },
          valid_from: { kind: :float, required: true },
          invalidated_at: { kind: :float, null: true, required: true }
        }.freeze,
        "MemoryQuestion" => {
          holds: { kind: :list, items: { kind: :str }, required: true },
          asks: { kind: :str, required: true },
          expects: { kind: :list, items: { kind: :str }, required: true }
        }.freeze,
        "MemoryMiss" => {
          asks: { kind: :str, required: true },
          missing: { kind: :list, items: { kind: :str }, required: true },
          found: { kind: :list, items: { kind: :str }, required: true }
        }.freeze,
        "ExtractionExpected" => {
          writes: { kind: :list, items: { kind: :str }, default: [] },
          never: { kind: :list, items: { kind: :str }, default: [] },
          never_says: { kind: :list, items: { kind: :str }, default: [] },
          invalidates: { kind: :list, items: { kind: :str }, default: [] }
        }.freeze,
        "ExtractionGolden" => {
          name: { kind: :str, required: true },
          said: { kind: :list, items: { kind: :tuple, members: [{ kind: :str }, { kind: :str }] }, required: true },
          holds: { kind: :list, items: { kind: :str }, default: [] },
          plants: { kind: :list, items: { kind: :str }, default: [] },
          channel: { kind: :ref, ref: "Channel", default: "phone" },
          expect: { kind: :ref, ref: "ExtractionExpected", default: {} }
        }.freeze,
        "ExtractionBroke" => {
          check: { kind: :str, required: true },
          detail: { kind: :str, required: true }
        }.freeze,
        "ExtractionJudged" => {
          name: { kind: :str, required: true },
          held: { kind: :bool, required: true },
          wrote: { kind: :list, items: { kind: :str }, default: [] },
          refused: { kind: :list, items: { kind: :str }, default: [] },
          broke: { kind: :list, items: { kind: :ref, ref: "ExtractionBroke" }, default: [] }
        }.freeze,
        "UserTurn" => {
          role: { kind: :const, const: "user", required: true },
          speech_id: { kind: :str, required: true },
          item_id: { kind: :str },
          text: { kind: :str, required: true },
          language: { kind: :str },
          transcript_confidence: { kind: :float },
          metrics: { kind: :ref, ref: "UserTurnMetrics", required: true }
        }.freeze,
        "AgentTurn" => {
          role: { kind: :const, const: "agent", required: true },
          speech_id: { kind: :str, required: true },
          item_id: { kind: :str },
          text: { kind: :str, required: true },
          interrupted: { kind: :bool, required: true },
          metrics: { kind: :ref, ref: "AgentTurnMetrics", required: true }
        }.freeze,
        "ToolRun" => {
          call_id: { kind: :str, required: true },
          name: { kind: :str, required: true },
          arguments: { kind: :json, required: true },
          speech_id: { kind: :str },
          status: { kind: :enum, values: %w[running done failed], required: true },
          output: { kind: :any },
          error: { kind: :str },
          summary: { kind: :str },
          duration_s: { kind: :float },
          seq: { kind: :int, required: true }
        }.freeze,
        "PromptBlockState" => {
          hash: { kind: :str, required: true },
          chars: { kind: :int, required: true },
          seq: { kind: :int, required: true }
        }.freeze,
        "Confirm" => {
          tool: { kind: :str, required: true },
          call_id: { kind: :str, required: true },
          audience: { kind: :str, required: true },
          phrase: { kind: :str, required: true },
          status: { kind: :enum, values: %w[pending granted declined], required: true },
          said: { kind: :str },
          reason: { kind: :str }
        }.freeze,
        "Handoff" => {
          active: { kind: :bool, required: true },
          by: { kind: :ref, null: true, ref: "Supervisor", required: true }
        }.freeze,
        "TransferState" => {
          to: { kind: :str, required: true },
          mode: { kind: :ref, null: true, ref: "TransferMode" },
          status: { kind: :enum, values: %w[requested done failed], required: true },
          by: { kind: :enum, values: %w[agent supervisor], required: true }
        }.freeze,
        "AttentionState" => {
          reason: { kind: :str, required: true },
          wait_s: { kind: :float, required: true },
          status: { kind: :enum, values: %w[open answered lapsed], required: true },
          asked_at: { kind: :float, required: true },
          by: { kind: :ref, null: true, ref: "Supervisor", required: true }
        }.freeze,
        "LiveTranscript" => {
          user: { kind: :str, null: true, required: true },
          agent: { kind: :str, null: true, required: true }
        }.freeze,
        "Gap" => {
          from_seq: { kind: :int, required: true },
          to_seq: { kind: :int, required: true }
        }.freeze,
        "LoggedError" => {
          seq: { kind: :int, required: true },
          code: { kind: :str, required: true },
          message: { kind: :str, required: true }
        }.freeze,
        "Participant" => {
          identity: { kind: :str, required: true },
          kind: { kind: :ref, ref: "ParticipantKind", required: true },
          name: { kind: :str },
          joined_at: { kind: :float, required: true },
          speaking: { kind: :bool, required: true },
          attributes: { kind: :json, required: true }
        }.freeze,
        "Room" => {
          name: { kind: :str, required: true },
          sid: { kind: :str, required: true },
          participants: { kind: :list, items: { kind: :ref, ref: "Participant" }, required: true },
          caller: { kind: :str, null: true, required: true }
        }.freeze,
        "ReceivedEvent" => {
          seq: { kind: :int, required: true },
          name: { kind: :str, required: true },
          source: { kind: :ref, ref: "EventSource", required: true },
          identity: { kind: :str }
        }.freeze,
        "CustomNote" => {
          seq: { kind: :int, required: true },
          name: { kind: :str, required: true },
          data: { kind: :json, required: true }
        }.freeze,
        "State" => {
          seq: { kind: :int, required: true },
          agent: { kind: :str, required: true },
          call: { kind: :str, null: true, required: true },
          status: { kind: :ref, ref: "CallStatus", required: true },
          channel: { kind: :ref, null: true, ref: "Channel", required: true },
          direction: { kind: :ref, null: true, ref: "Direction", required: true },
          from: { kind: :str, null: true, required: true },
          to: { kind: :str, null: true, required: true },
          caller: { kind: :ref, null: true, ref: "Contact", required: true },
          room: { kind: :ref, null: true, ref: "Room", required: true },
          started_at: { kind: :float, null: true, required: true },
          ended_at: { kind: :float, null: true, required: true },
          end_reason: { kind: :ref, null: true, ref: "EndReason", required: true },
          outcome: { kind: :str, null: true, required: true },
          user_state: { kind: :ref, null: true, ref: "UserState", required: true },
          agent_state: { kind: :ref, null: true, ref: "AgentState", required: true },
          live: { kind: :ref, ref: "LiveTranscript", required: true },
          turns: { kind: :list, items: { kind: :ref, ref: "Turn" }, required: true },
          metrics: { kind: :ref, ref: "CollectedMetrics", required: true },
          tools: { kind: :list, items: { kind: :ref, ref: "ToolRun" }, required: true },
          app_state: { kind: :json, required: true },
          events: { kind: :list, items: { kind: :ref, ref: "ReceivedEvent" }, required: true },
          prompt: { kind: :ref, ref: "PromptState", required: true },
          tools_visible: { kind: :list, items: { kind: :str }, required: true },
          confirms: { kind: :list, items: { kind: :ref, ref: "Confirm" }, required: true },
          memory: { kind: :list, items: { kind: :ref, ref: "MemoryOp" }, required: true },
          sources: { kind: :list, items: { kind: :ref, ref: "DocSource" }, required: true },
          handoff: { kind: :ref, ref: "Handoff", required: true },
          held: { kind: :bool, required: true },
          muted: { kind: :bool, required: true },
          transfer: { kind: :ref, null: true, ref: "TransferState", required: true },
          attention: { kind: :ref, null: true, ref: "AttentionState" },
          usage: { kind: :list, items: { kind: :ref, ref: "ModelUsage" }, required: true },
          cost: { kind: :ref, null: true, ref: "Cost", required: true },
          routes: { kind: :list, items: { kind: :ref, ref: "Route" }, required: true },
          gaps: { kind: :list, items: { kind: :ref, ref: "Gap" }, required: true },
          errors: { kind: :list, items: { kind: :ref, ref: "LoggedError" }, required: true },
          custom: { kind: :list, items: { kind: :ref, ref: "CustomNote" }, required: true }
        }.freeze,
        "SayVerb" => {
          verb: { kind: :const, const: "say", required: true },
          text: { kind: :str, required: true }
        }.freeze,
        "WhisperVerb" => {
          verb: { kind: :const, const: "whisper", required: true },
          text: { kind: :str, required: true }
        }.freeze,
        "TakeoverVerb" => {
          verb: { kind: :const, const: "takeover", required: true }
        }.freeze,
        "ReleaseVerb" => {
          verb: { kind: :const, const: "release", required: true }
        }.freeze,
        "TransferVerb" => {
          verb: { kind: :const, const: "transfer", required: true },
          to: { kind: :str, required: true },
          mode: { kind: :ref, ref: "TransferMode" }
        }.freeze,
        "EndVerb" => {
          verb: { kind: :const, const: "end", required: true },
          reason: { kind: :str }
        }.freeze,
        "DevRefusal" => {
          status: { kind: :int, required: true },
          detail: { kind: :str, required: true }
        }.freeze,
        "JudgedBy" => {
          provider: { kind: :str, null: true, required: true },
          model: { kind: :str, null: true, required: true },
          criteria: { kind: :str, required: true }
        }.freeze,
        "Judgment" => {
          name: { kind: :str, required: true },
          verdict: { kind: :ref, ref: "ScoreVerdict", required: true },
          criteria: { kind: :str, required: true },
          reason: { kind: :str, required: true },
          evidence: { kind: :ref, ref: "JudgmentEvidence", required: true },
          choice: { kind: :str, null: true },
          score: { kind: :int, null: true }
        }.freeze,
        "JudgmentEvidence" => {
          seqs: { kind: :list, items: { kind: :int }, required: true },
          said: { kind: :str }
        }.freeze,
        "StateCauseTool" => {
          kind: { kind: :const, const: "tool", required: true },
          tool: { kind: :str, required: true },
          call_id: { kind: :str, required: true }
        }.freeze,
        "StateCauseEvent" => {
          kind: { kind: :const, const: "event", required: true },
          name: { kind: :str, required: true },
          seq: { kind: :int, required: true }
        }.freeze,
      }.freeze
    end
  end
end
