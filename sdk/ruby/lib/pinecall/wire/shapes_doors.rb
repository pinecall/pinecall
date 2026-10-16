# frozen_string_literal: true

# The bodies and answers of the doors this gem calls: knowledge, memory, the agent's config.

module Pinecall
  module Wire
    module Shapes
      DOORS = {
        "ToolSpec" => {
          name: { kind: :str, required: true },
          description: { kind: :str, required: true },
          parameters: { kind: :json, required: true },
          side_effect: { kind: :enum, values: %w[read write irreversible], default: "read" },
          confirm: { kind: :str },
          announce: { kind: :str },
          pii: { kind: :list, items: { kind: :str } },
          timeout_s: { kind: :float }
        }.freeze,
        "AgentConfig" => {
          prompt: { kind: :list, items: { kind: :ref, ref: "PromptBlockSpec" } },
          language: { kind: :str },
          greeting: { kind: :ref, ref: "GreetingConfig" },
          voice: { kind: :ref, ref: "VoiceConfig" },
          llm: { kind: :ref, ref: "ModelConfig" },
          stt: { kind: :ref, ref: "ModelConfig" },
          judge: { kind: :ref, ref: "ModelConfig" },
          turn: { kind: :ref, ref: "TurnConfig" },
          says: { kind: :list, items: { kind: :ref, ref: "Pronunciation" } },
          hears: { kind: :list, items: { kind: :str } },
          knowledge: { kind: :ref, ref: "KnowledgeFile" },
          docs: { kind: :ref, ref: "DocsConfig" },
          memory: { kind: :ref, ref: "MemoryConfig" },
          hangup: { kind: :ref, ref: "HangupConfig" },
          record: { kind: :bool, default: true },
          tools: { kind: :list, items: { kind: :ref, ref: "ToolSpec" } },
          uses_knowledge: { kind: :bool, default: false },
          state_fields: { kind: :list, items: { kind: :ref, ref: "StateFieldSpec" } },
          view: { kind: :ref, ref: "ViewSpec" },
          events: { kind: :list, items: { kind: :ref, ref: "EventSpec" } }
        }.freeze,
        "KnowledgePush" => {
          files: { kind: :list, items: { kind: :ref, ref: "KnowledgeFile" }, required: true }
        }.freeze,
        "KnowledgeGolden" => {
          questions: { kind: :list, items: { kind: :ref, ref: "GoldenQuestion" }, required: true },
          k: { kind: :int }
        }.freeze,
        "KnowledgeScore" => {
          base: { kind: :str, required: true },
          model: { kind: :str, required: true },
          questions: { kind: :int, required: true },
          k: { kind: :int, required: true },
          recall_at_k: { kind: :float, required: true },
          ndcg_at_10: { kind: :float, required: true },
          took_ms: { kind: :float, required: true },
          misses: { kind: :list, items: { kind: :ref, ref: "GoldenMiss" }, required: true }
        }.freeze,
        "KnowledgePushed" => {
          base: { kind: :str, required: true },
          chunks: { kind: :int, required: true },
          took_ms: { kind: :float, required: true }
        }.freeze,
        "KnowledgeList" => {
          bases: { kind: :list, items: { kind: :ref, ref: "KnowledgeBase" }, required: true }
        }.freeze,
        "ContactMemory" => {
          facts: { kind: :list, items: { kind: :ref, ref: "ContactFact" }, required: true }
        }.freeze,
        "Forgotten" => {
          forgotten: { kind: :int, required: true }
        }.freeze,
        "MemoryGolden" => {
          questions: { kind: :list, items: { kind: :ref, ref: "MemoryQuestion" }, required: true },
          k: { kind: :int }
        }.freeze,
        "MemoryScore" => {
          model: { kind: :str, required: true },
          questions: { kind: :int, required: true },
          k: { kind: :int, required: true },
          recall_at_k: { kind: :float, required: true },
          ndcg_at_10: { kind: :float, required: true },
          took_ms: { kind: :float, required: true },
          misses: { kind: :list, items: { kind: :ref, ref: "MemoryMiss" }, required: true }
        }.freeze,
        "ExtractionCases" => {
          cases: { kind: :list, items: { kind: :ref, ref: "ExtractionGolden" }, required: true }
        }.freeze,
        "ExtractionRun" => {
          agent: { kind: :str, required: true },
          model: { kind: :str, required: true },
          cases: { kind: :int, required: true },
          held: { kind: :int, required: true },
          took_ms: { kind: :float, required: true },
          results: { kind: :list, items: { kind: :ref, ref: "ExtractionJudged" }, required: true }
        }.freeze,
      }.freeze
    end
  end
end
