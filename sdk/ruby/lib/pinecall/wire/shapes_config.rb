# frozen_string_literal: true

# An agent as its app declares it: voice, models, turns, tools, views, docs, memory.

module Pinecall
  module Wire
    module Shapes
      CONFIG = {
        "PromptBlockSpec" => {
          name: { kind: :str, required: true, pattern: "^[a-z][a-z0-9_]*$" },
          region: { kind: :ref, ref: "PromptRegion", required: true }
        }.freeze,
        "VoiceConfig" => {
          name: { kind: :str },
          provider: { kind: :str },
          model: { kind: :str },
          voice_id: { kind: :str },
          builds: { kind: :str },
          options: { kind: :json }
        }.freeze,
        "ModelConfig" => {
          provider: { kind: :str, required: true },
          model: { kind: :str, required: true },
          temperature: { kind: :float },
          builds: { kind: :str },
          options: { kind: :json },
          end_of_turn: { kind: :enum, values: %w[stt livekit smart-turn] }
        }.freeze,
        "TurnConfig" => {
          min_interruption_words: { kind: :int },
          endpointing_ms: { kind: :int },
          eot_threshold: { kind: :float },
          eager_eot_threshold: { kind: :float }
        }.freeze,
        "Pronunciation" => {
          word: { kind: :str, required: true },
          spoken: { kind: :str, required: true }
        }.freeze,
        "StateFieldSpec" => {
          name: { kind: :str, required: true },
          visibility: { kind: :ref, ref: "Visibility", required: true }
        }.freeze,
        "ViewSpec" => {
          name: { kind: :str, required: true }
        }.freeze,
        "EventSpec" => {
          name: { kind: :str, required: true },
          from: { kind: :list, items: { kind: :ref, ref: "EventSource" }, required: true }
        }.freeze,
        "KnowledgeFile" => {
          path: { kind: :str, required: true },
          text: { kind: :str, required: true }
        }.freeze,
        "DocsConfig" => {
          base: { kind: :str, required: true },
          mode: { kind: :ref, ref: "DocsMode", default: "retrieved" },
          k: { kind: :int, default: 8 },
          min_score: { kind: :float }
        }.freeze,
        "GreetingConfig" => {
          say: { kind: :str },
          reply: { kind: :str },
          allow_interruptions: { kind: :bool }
        }.freeze,
        "HangupConfig" => {
          when: { kind: :str, default: "" }
        }.freeze,
        "MemoryConfig" => {
          remember: { kind: :list, items: { kind: :str }, default: [] },
          forget: { kind: :list, items: { kind: :str }, default: [] }
        }.freeze,
      }.freeze
    end
  end
end
