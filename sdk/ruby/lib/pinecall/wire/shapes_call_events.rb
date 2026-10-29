# frozen_string_literal: true

# The shape of each event's data in a call's life and in the agent that holds it.

module Pinecall
  module Wire
    module Shapes
      CALL_EVENTS = {
        "AgentConfigured" => {
          changed: { kind: :list, items: { kind: :str }, required: true }
        }.freeze,
        "AgentDetached" => {
          app: { kind: :str, required: true },
          env: { kind: :ref, ref: "Env", required: true },
          left: { kind: :bool, required: true }
        }.freeze,
        "AgentDraining" => {
          app: { kind: :str, required: true },
          env: { kind: :ref, ref: "Env", required: true },
          handed: { kind: :int, required: true },
          parked: { kind: :int, required: true }
        }.freeze,
        "AgentRegistered" => {
          routes: { kind: :list, items: { kind: :ref, ref: "Route" }, required: true },
          app: { kind: :str, required: true },
          sdk: { kind: :str },
          env: { kind: :ref, ref: "Env" }
        }.freeze,
        "AgentStateChanged" => {
          state: { kind: :ref, ref: "AgentState", required: true }
        }.freeze,
        "AgentTranscript" => {
          speech_id: { kind: :str, required: true },
          text: { kind: :str, required: true },
          final: { kind: :bool, required: true },
          start: { kind: :float },
          end: { kind: :float }
        }.freeze,
        "CallAttached" => {
          app: { kind: :str, required: true },
          started: { kind: :ref, ref: "CallStarted", required: true },
          state: { kind: :json, required: true },
          seq: { kind: :int, required: true },
          claimed: { kind: :str, null: true }
        }.freeze,
        "CallClaimed" => {
          code: { kind: :str, required: true },
          via: { kind: :enum, values: %w[keypad agent], required: true }
        }.freeze,
        "CallDialing" => {
          channel: { kind: :ref, ref: "Channel", required: true },
          from: { kind: :str, required: true },
          to: { kind: :str, required: true },
          run: { kind: :str, null: true },
          caller: { kind: :ref, null: true, ref: "Contact", required: true },
          external_id: { kind: :str },
          asked_by: { kind: :str }
        }.freeze,
        "CallEnded" => {
          reason: { kind: :ref, ref: "EndReason", required: true },
          ended_by: { kind: :ref, ref: "EndedBy", required: true },
          ended_at: { kind: :float, required: true },
          duration_s: { kind: :float, required: true }
        }.freeze,
        "CallLine" => {
          held: { kind: :bool, required: true },
          muted: { kind: :bool, required: true }
        }.freeze,
        "CallRinging" => {
          channel: { kind: :ref, ref: "Channel", required: true },
          from: { kind: :str, required: true },
          to: { kind: :str, required: true },
          route: { kind: :ref, ref: "Route", required: true },
          run: { kind: :str, null: true },
          caller: { kind: :ref, null: true, ref: "Contact", required: true },
          external_id: { kind: :str }
        }.freeze,
        "CallScore" => {
          passed: { kind: :bool },
          not_judged: { kind: :str },
          judges: { kind: :list, items: { kind: :ref, ref: "Judgment" }, required: true },
          panel: { kind: :list, items: { kind: :str } },
          judge_calls: { kind: :int, required: true },
          evals: { kind: :int },
          own_key: { kind: :bool },
          judge_cost_usd: { kind: :float },
          judged_by: { kind: :ref, ref: "JudgedBy" }
        }.freeze,
        "CallStarted" => {
          channel: { kind: :ref, ref: "Channel", required: true },
          direction: { kind: :ref, ref: "Direction", required: true },
          from: { kind: :str, required: true },
          to: { kind: :str, required: true },
          run: { kind: :str, null: true },
          persona: { kind: :str, null: true },
          expects: { kind: :list, items: { kind: :str }, null: true },
          caller: { kind: :ref, null: true, ref: "Contact", required: true },
          started_at: { kind: :float, required: true },
          env: { kind: :ref, ref: "Env" },
          worker: { kind: :str, null: true },
          medium: { kind: :ref, ref: "Medium", null: true },
          state: { kind: :json },
          today: { kind: :str, null: true },
          metadata: { kind: :json }
        }.freeze,
        "CallSummary" => {
          reason: { kind: :ref, ref: "EndReason", required: true },
          outcome: { kind: :str, required: true },
          duration_s: { kind: :float, required: true },
          turns: { kind: :int, required: true },
          usage: { kind: :list, items: { kind: :ref, ref: "ModelUsage" }, required: true },
          cost: { kind: :ref, ref: "Cost", required: true },
          recording: { kind: :str },
          simulated: { kind: :bool },
          run: { kind: :str, null: true }
        }.freeze,
        "CallTransferred" => {
          to: { kind: :str, required: true },
          mode: { kind: :ref, null: true, ref: "TransferMode" },
          ok: { kind: :bool, required: true },
          error: { kind: :str }
        }.freeze,
        "CallbackRequested" => {
          channel: { kind: :ref, ref: "Channel", required: true },
          number: { kind: :str, required: true },
          via: { kind: :enum, values: %w[overflow widget agent], required: true },
          call: { kind: :str, null: true, required: true },
          when: { kind: :str },
          note: { kind: :str },
          contact: { kind: :ref, null: true, ref: "Contact", required: true }
        }.freeze,
        "AgentTurnEnded" => {
          speech_id: { kind: :str, required: true },
          item_id: { kind: :str },
          text: { kind: :str, required: true },
          interrupted: { kind: :bool, required: true },
          metrics: { kind: :ref, ref: "AgentTurnMetrics", required: true }
        }.freeze,
        "AgentWaiting" => {
          speech_id: { kind: :str, required: true },
          interrupted: { kind: :bool, required: true }
        }.freeze,
      }.freeze
    end
  end
end
