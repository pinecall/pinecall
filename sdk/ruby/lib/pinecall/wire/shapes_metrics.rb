# frozen_string_literal: true

# What livekit measured for a turn and a model, and the usage a call is billed by.

module Pinecall
  module Wire
    module Shapes
      METRICS = {
        "RealtimeCachedTokenDetails" => {
          audio_tokens: { kind: :int },
          text_tokens: { kind: :int },
          image_tokens: { kind: :int }
        }.freeze,
        "RealtimeInputTokenDetails" => {
          audio_tokens: { kind: :int },
          text_tokens: { kind: :int },
          image_tokens: { kind: :int },
          cached_tokens: { kind: :int },
          cached_tokens_details: { kind: :ref, null: true, ref: "RealtimeCachedTokenDetails" }
        }.freeze,
        "RealtimeOutputTokenDetails" => {
          text_tokens: { kind: :int },
          audio_tokens: { kind: :int },
          image_tokens: { kind: :int }
        }.freeze,
        "UserTurnMetrics" => {
          started_speaking_at: { kind: :float },
          stopped_speaking_at: { kind: :float },
          transcription_delay: { kind: :float },
          end_of_turn_delay: { kind: :float },
          on_user_turn_completed_delay: { kind: :float },
          stt_metadata: { kind: :ref, ref: "TurnMetadata" }
        }.freeze,
        "AgentTurnMetrics" => {
          started_speaking_at: { kind: :float },
          stopped_speaking_at: { kind: :float },
          llm_node_ttft: { kind: :float },
          llm_node_tps: { kind: :float },
          llm_node_ttfs: { kind: :float },
          tts_node_ttfb: { kind: :float },
          playback_latency: { kind: :float },
          e2e_latency: { kind: :float },
          provider_request_ids: { kind: :list, items: { kind: :str } },
          llm_metadata: { kind: :ref, ref: "TurnMetadata" },
          tts_metadata: { kind: :ref, ref: "TurnMetadata" }
        }.freeze,
        "LLMModelUsage" => {
          type: { kind: :const, const: "llm_usage", required: true },
          provider: { kind: :str, required: true },
          model: { kind: :str, required: true },
          input_tokens: { kind: :int },
          input_cached_tokens: { kind: :int },
          input_cache_creation_tokens: { kind: :int },
          input_audio_tokens: { kind: :int },
          input_cached_audio_tokens: { kind: :int },
          input_text_tokens: { kind: :int },
          input_cached_text_tokens: { kind: :int },
          input_image_tokens: { kind: :int },
          input_cached_image_tokens: { kind: :int },
          output_tokens: { kind: :int },
          output_audio_tokens: { kind: :int },
          output_text_tokens: { kind: :int },
          output_reasoning_tokens: { kind: :int },
          session_duration: { kind: :float }
        }.freeze,
        "TTSModelUsage" => {
          type: { kind: :const, const: "tts_usage", required: true },
          provider: { kind: :str, required: true },
          model: { kind: :str, required: true },
          input_tokens: { kind: :int },
          output_tokens: { kind: :int },
          characters_count: { kind: :int },
          audio_duration: { kind: :float }
        }.freeze,
        "STTModelUsage" => {
          type: { kind: :const, const: "stt_usage", required: true },
          provider: { kind: :str, required: true },
          model: { kind: :str, required: true },
          input_tokens: { kind: :int },
          output_tokens: { kind: :int },
          audio_duration: { kind: :float }
        }.freeze,
        "InterruptionModelUsage" => {
          type: { kind: :const, const: "interruption_usage", required: true },
          provider: { kind: :str, required: true },
          model: { kind: :str, required: true },
          total_requests: { kind: :int }
        }.freeze,
        "EOTModelUsage" => {
          type: { kind: :const, const: "eot_usage", required: true },
          provider: { kind: :str, required: true },
          model: { kind: :str, required: true },
          total_requests: { kind: :int }
        }.freeze,
        "CollectedMetrics" => {
          llm: { kind: :list, items: { kind: :ref, ref: "LLMMetrics" }, required: true },
          stt: { kind: :list, items: { kind: :ref, ref: "STTMetrics" }, required: true },
          tts: { kind: :list, items: { kind: :ref, ref: "TTSMetrics" }, required: true },
          vad: { kind: :list, items: { kind: :ref, ref: "VADMetrics" }, required: true },
          eou: { kind: :list, items: { kind: :ref, ref: "EOUMetrics" }, required: true },
          eot: { kind: :list, items: { kind: :ref, ref: "EOTInferenceMetrics" }, required: true },
          interruption: { kind: :list, items: { kind: :ref, ref: "InterruptionMetrics" }, required: true },
          realtime: { kind: :list, items: { kind: :ref, ref: "RealtimeModelMetrics" }, required: true },
          avatar: { kind: :list, items: { kind: :ref, ref: "AvatarMetrics" }, required: true }
        }.freeze,
      }.freeze
    end
  end
end
