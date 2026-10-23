# frozen_string_literal: true

# The shape of each event's data during a call: talk, tools, the desk, memory, errors.

module Pinecall
  module Wire
    module Shapes
      EVENTS = {
        "ToolResult" => {
          call_id: { kind: :str, required: true },
          name: { kind: :str, required: true },
          output: { kind: :any },
          error: { kind: :str },
          summary: { kind: :str },
          duration_s: { kind: :float }
        }.freeze,
        "LLMMetrics" => {
          type: { kind: :const, const: "llm_metrics", required: true },
          label: { kind: :str, required: true },
          request_id: { kind: :str, required: true },
          timestamp: { kind: :float, required: true },
          duration: { kind: :float, required: true },
          ttft: { kind: :float, required: true },
          cancelled: { kind: :bool, required: true },
          completion_tokens: { kind: :int, required: true },
          prompt_tokens: { kind: :int, required: true },
          prompt_cached_tokens: { kind: :int, required: true },
          cache_creation_tokens: { kind: :int },
          reasoning_tokens: { kind: :int },
          total_tokens: { kind: :int, required: true },
          tokens_per_second: { kind: :float, required: true },
          speech_id: { kind: :str, null: true },
          metadata: { kind: :ref, null: true, ref: "Metadata" }
        }.freeze,
        "STTMetrics" => {
          type: { kind: :const, const: "stt_metrics", required: true },
          label: { kind: :str, required: true },
          request_id: { kind: :str, required: true },
          timestamp: { kind: :float, required: true },
          duration: { kind: :float, required: true },
          audio_duration: { kind: :float, required: true },
          input_tokens: { kind: :int },
          output_tokens: { kind: :int },
          streamed: { kind: :bool, required: true },
          acquire_time: { kind: :float },
          connection_reused: { kind: :bool },
          metadata: { kind: :ref, null: true, ref: "Metadata" }
        }.freeze,
        "TTSMetrics" => {
          type: { kind: :const, const: "tts_metrics", required: true },
          label: { kind: :str, required: true },
          request_id: { kind: :str, required: true },
          timestamp: { kind: :float, required: true },
          ttfb: { kind: :float, required: true },
          duration: { kind: :float, required: true },
          audio_duration: { kind: :float, required: true },
          cancelled: { kind: :bool, required: true },
          characters_count: { kind: :int, required: true },
          input_tokens: { kind: :int },
          output_tokens: { kind: :int },
          streamed: { kind: :bool, required: true },
          acquire_time: { kind: :float },
          connection_reused: { kind: :bool },
          segment_id: { kind: :str, null: true },
          speech_id: { kind: :str, null: true },
          metadata: { kind: :ref, null: true, ref: "Metadata" }
        }.freeze,
        "VADMetrics" => {
          type: { kind: :const, const: "vad_metrics", required: true },
          label: { kind: :str, required: true },
          timestamp: { kind: :float, required: true },
          idle_time: { kind: :float, required: true },
          inference_duration_total: { kind: :float, required: true },
          inference_count: { kind: :int, required: true },
          metadata: { kind: :ref, null: true, ref: "Metadata" }
        }.freeze,
        "EOUMetrics" => {
          type: { kind: :const, const: "eou_metrics", required: true },
          timestamp: { kind: :float, required: true },
          end_of_utterance_delay: { kind: :float, required: true },
          transcription_delay: { kind: :float, required: true },
          on_user_turn_completed_delay: { kind: :float, required: true },
          speech_id: { kind: :str, null: true },
          metadata: { kind: :ref, null: true, ref: "Metadata" }
        }.freeze,
        "EOTInferenceMetrics" => {
          type: { kind: :const, const: "eot_inference_metrics", required: true },
          timestamp: { kind: :float, required: true },
          total_duration: { kind: :float, required: true },
          detection_delay: { kind: :float, required: true },
          prediction_duration: { kind: :float, required: true },
          num_requests: { kind: :int },
          metadata: { kind: :ref, null: true, ref: "Metadata" }
        }.freeze,
        "InterruptionMetrics" => {
          type: { kind: :const, const: "interruption_metrics", required: true },
          timestamp: { kind: :float, required: true },
          total_duration: { kind: :float, required: true },
          prediction_duration: { kind: :float, required: true },
          detection_delay: { kind: :float, required: true },
          num_interruptions: { kind: :int, required: true },
          num_backchannels: { kind: :int, required: true },
          num_requests: { kind: :int, required: true },
          metadata: { kind: :ref, null: true, ref: "Metadata" }
        }.freeze,
        "RealtimeModelMetrics" => {
          type: { kind: :const, const: "realtime_model_metrics", required: true },
          label: { kind: :str },
          request_id: { kind: :str, required: true },
          timestamp: { kind: :float, required: true },
          duration: { kind: :float },
          session_duration: { kind: :float },
          ttft: { kind: :float },
          cancelled: { kind: :bool },
          input_tokens: { kind: :int },
          output_tokens: { kind: :int },
          total_tokens: { kind: :int },
          tokens_per_second: { kind: :float },
          input_token_details: { kind: :ref, ref: "RealtimeInputTokenDetails", required: true },
          output_token_details: { kind: :ref, ref: "RealtimeOutputTokenDetails", required: true },
          acquire_time: { kind: :float },
          connection_reused: { kind: :bool },
          metadata: { kind: :ref, null: true, ref: "Metadata" }
        }.freeze,
        "AvatarMetrics" => {
          type: { kind: :const, const: "avatar_metrics", required: true },
          timestamp: { kind: :float, required: true },
          playback_latency: { kind: :float },
          session_started_time: { kind: :float, null: true },
          avatar_joined_time: { kind: :float, null: true },
          metadata: { kind: :ref, null: true, ref: "Metadata" }
        }.freeze,
        "RoomOpened" => {
          name: { kind: :str, required: true },
          sid: { kind: :str, required: true },
          channel: { kind: :ref, ref: "Channel", required: true }
        }.freeze,
        "ParticipantJoined" => {
          identity: { kind: :str, required: true },
          kind: { kind: :ref, ref: "ParticipantKind", required: true },
          name: { kind: :str },
          attributes: { kind: :json, required: true }
        }.freeze,
        "ParticipantLeft" => {
          identity: { kind: :str, required: true },
          reason: { kind: :str, required: true }
        }.freeze,
        "ParticipantSpeaking" => {
          identity: { kind: :str, required: true },
          speaking: { kind: :bool, required: true }
        }.freeze,
        "TrackPublished" => {
          identity: { kind: :str, required: true },
          kind: { kind: :ref, ref: "TrackKind", required: true },
          source: { kind: :ref, ref: "TrackSource", required: true }
        }.freeze,
        "TrackUnpublished" => {
          identity: { kind: :str, required: true },
          kind: { kind: :ref, ref: "TrackKind", required: true },
          source: { kind: :ref, ref: "TrackSource", required: true }
        }.freeze,
        "EventReceived" => {
          name: { kind: :str, required: true },
          data: { kind: :json, required: true },
          source: { kind: :ref, ref: "EventSource", required: true },
          identity: { kind: :str }
        }.freeze,
        "RoomSent" => {
          topic: { kind: :str, required: true },
          to: { kind: :str },
          bytes: { kind: :int, required: true }
        }.freeze,
        "AttentionAnswered" => {
          ok: { kind: :bool, required: true },
          by: { kind: :ref, null: true, ref: "Supervisor", required: true },
          error: { kind: :str }
        }.freeze,
        "AttentionRequested" => {
          reason: { kind: :str, required: true },
          wait_s: { kind: :float, required: true }
        }.freeze,
        "CodeClaimed" => {
          code: { kind: :str, required: true },
          call: { kind: :str, null: true, required: true }
        }.freeze,
        "CodeIssued" => {
          code: { kind: :str, required: true },
          env: { kind: :ref, ref: "Env", required: true },
          expires_at: { kind: :float, required: true },
          log: { kind: :ref, ref: "Projection", required: true }
        }.freeze,
        "ConfirmDeclined" => {
          tool: { kind: :str, required: true },
          call_id: { kind: :str, required: true },
          audience: { kind: :str, required: true },
          said: { kind: :str },
          reason: { kind: :enum, values: %w[no timeout changed cancelled], required: true }
        }.freeze,
        "ConfirmGranted" => {
          tool: { kind: :str, required: true },
          call_id: { kind: :str, required: true },
          audience: { kind: :str, required: true },
          said: { kind: :str, required: true },
          ttl_s: { kind: :int, required: true }
        }.freeze,
        "ConfirmRequest" => {
          tool: { kind: :str, required: true },
          call_id: { kind: :str, required: true },
          arguments: { kind: :json, required: true },
          audience: { kind: :str, required: true },
          phrase: { kind: :str, required: true },
          ttl_s: { kind: :int, required: true }
        }.freeze,
        "CreditsExhausted" => {
          org: { kind: :str, required: true },
          quota: { kind: :enum, values: %w[minutes messages agents concurrent_calls memory_facts knowledge_chunks numbers seats llm_tokens hosted_apps evals simulations budget_usd], required: true },
          used: { kind: :float, required: true },
          limit: { kind: :int, required: true }
        }.freeze,
        "EvalsSpent" => {
          kind: { kind: :enum, values: %w[try generate propose], required: true },
          name: { kind: :str, required: true },
          env: { kind: :ref, ref: "Env", required: true },
          calls: { kind: :list, items: { kind: :str }, required: true },
          evals: { kind: :int, required: true },
          judge_calls: { kind: :int, required: true },
          judge_cost_usd: { kind: :float, null: true },
          own_key: { kind: :bool }
        }.freeze,
        "Custom" => {
          name: { kind: :str, required: true },
          data: { kind: :json, required: true }
        }.freeze,
        "DevRequest" => {
          id: { kind: :str, required: true },
          verb: { kind: :ref, ref: "DevVerb", required: true },
          data: { kind: :json, required: true }
        }.freeze,
        "DocsSources" => {
          query: { kind: :str, required: true },
          sources: { kind: :list, items: { kind: :ref, ref: "DocSource" }, required: true },
          took_ms: { kind: :float, required: true },
          speech_id: { kind: :str }
        }.freeze,
        "DtmfReceived" => {
          digit: { kind: :enum, values: %w[0 1 2 3 4 5 6 7 8 9 * #], required: true },
          code: { kind: :int, required: true }
        }.freeze,
        "ErrorEvent" => {
          code: { kind: :str, required: true },
          message: { kind: :str, required: true },
          command: { kind: :str },
          id: { kind: :str },
          recoverable: { kind: :bool, required: true }
        }.freeze,
        "FleetFull" => {
          channel: { kind: :ref, ref: "Channel", required: true },
          workers: { kind: :int, required: true },
          active: { kind: :int, required: true }
        }.freeze,
        "AppFailed" => {
          app: { kind: :str, required: true },
          host: { kind: :str, required: true },
          release: { kind: :int, null: true },
          why: { kind: :str, required: true }
        }.freeze,
        "ReleaseChanged" => {
          app: { kind: :str, required: true },
          release: { kind: :int, required: true }
        }.freeze,
        "RunChanged" => {
          run: { kind: :str, required: true },
          agent: { kind: :str, required: true },
          finished: { kind: :bool, required: true }
        }.freeze,
        "WorkerChanged" => {
          worker: { kind: :str, required: true },
          fleet: { kind: :str, required: true },
          up: { kind: :bool, required: true },
          cordoned: { kind: :bool, required: true }
        }.freeze,
        "ToolRan" => {
          call: { kind: :str, required: true },
          agent: { kind: :str, required: true },
          name: { kind: :str, required: true },
          duration_s: { kind: :float, null: true, required: true }
        }.freeze,
        "ToolFailed" => {
          call: { kind: :str, required: true },
          agent: { kind: :str, required: true },
          name: { kind: :str, required: true },
          duration_s: { kind: :float, null: true, required: true }
        }.freeze,
        "JudgeBroke" => {
          call: { kind: :str, required: true },
          agent: { kind: :str, required: true },
          judge: { kind: :str, required: true }
        }.freeze,
        "LogCaughtUp" => {
          seq: { kind: :int, required: true }
        }.freeze,
        "LogGap" => {
          from_seq: { kind: :int, required: true },
          to_seq: { kind: :int, required: true },
          snapshot: { kind: :ref, null: true, ref: "State", required: true }
        }.freeze,
        "MemoryOps" => {
          ops: { kind: :list, items: { kind: :ref, ref: "MemoryOp" }, required: true },
          speech_id: { kind: :str }
        }.freeze,
        "MessageTaken" => {
          message_id: { kind: :str, required: true },
          call: { kind: :str, null: true, required: true }
        }.freeze,
        "MessageWaiting" => {
          channel: { kind: :ref, ref: "Channel", required: true },
          env: { kind: :ref, ref: "Env", required: true },
          number: { kind: :str, required: true },
          phone_number_id: { kind: :str, required: true },
          from: { kind: :str, required: true },
          name: { kind: :str, null: true, required: true },
          message_id: { kind: :str, required: true },
          text: { kind: :str, required: true },
          received_at: { kind: :float, required: true }
        }.freeze,
        "Pong" => {
          ts: { kind: :float, required: true }
        }.freeze,
        "PromptChanged" => {
          name: { kind: :str, required: true },
          hash: { kind: :str, required: true },
          chars: { kind: :int, required: true }
        }.freeze,
        "SpendUnusual" => {
          org: { kind: :str, required: true },
          day: { kind: :str, required: true },
          today_usd: { kind: :float, required: true },
          usual_usd: { kind: :float, required: true },
          multiple: { kind: :float, required: true }
        }.freeze,
        "StateChanged" => {
          state: { kind: :json, required: true },
          changed: { kind: :list, items: { kind: :str }, required: true },
          cause: { kind: :ref, ref: "StateCause" }
        }.freeze,
        "SupervisorEnded" => {
          by: { kind: :ref, ref: "Supervisor", required: true },
          reason: { kind: :str }
        }.freeze,
        "SupervisorReleased" => {
          by: { kind: :ref, ref: "Supervisor", required: true }
        }.freeze,
        "SupervisorSaid" => {
          by: { kind: :ref, ref: "Supervisor", required: true },
          text: { kind: :str, required: true }
        }.freeze,
        "SupervisorTookOver" => {
          by: { kind: :ref, ref: "Supervisor", required: true }
        }.freeze,
        "SupervisorTransferred" => {
          by: { kind: :ref, ref: "Supervisor", required: true },
          to: { kind: :str, required: true },
          mode: { kind: :ref, null: true, ref: "TransferMode" }
        }.freeze,
        "SupervisorWhispered" => {
          by: { kind: :ref, ref: "Supervisor", required: true },
          text: { kind: :str, required: true }
        }.freeze,
        "ToolCall" => {
          call_id: { kind: :str, required: true },
          name: { kind: :str, required: true },
          arguments: { kind: :json, required: true },
          speech_id: { kind: :str }
        }.freeze,
        "ToolsChanged" => {
          visible: { kind: :list, items: { kind: :str }, required: true }
        }.freeze,
        "UserTurnEnded" => {
          speech_id: { kind: :str, required: true },
          item_id: { kind: :str },
          text: { kind: :str, required: true },
          language: { kind: :str },
          transcript_confidence: { kind: :float },
          metrics: { kind: :ref, ref: "UserTurnMetrics", required: true }
        }.freeze,
        "UserStateChanged" => {
          state: { kind: :ref, ref: "UserState", required: true }
        }.freeze,
        "UserTranscript" => {
          text: { kind: :str, required: true },
          final: { kind: :bool, required: true },
          language: { kind: :str },
          confidence: { kind: :float }
        }.freeze,
        "VendorSwitched" => {
          stage: { kind: :enum, values: %w[llm stt tts], required: true },
          vendor: { kind: :str, required: true },
          model: { kind: :str, required: true },
          available: { kind: :bool, required: true },
          serving: { kind: :str, required: true },
          serving_model: { kind: :str, required: true }
        }.freeze
      }.freeze
    end
  end
end
