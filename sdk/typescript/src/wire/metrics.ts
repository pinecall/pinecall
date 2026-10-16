/** The metrics livekit reports for a turn and a model, as the runtime writes them. */

import { z } from "zod";

/** Which model and provider produced a block. livekit's Metadata, nested exactly as it nests it. */
export const MetadataSchema = z.strictObject({
  model_name: z.string().nullable().nullish(),
  model_provider: z.string().nullable().nullish(),
});

/**
 * One LLM request, measured by the session's llm node. Two arrive for one reply when a tool ran in
 * between; they share the speech_id.
 */
export const LLMMetricsSchema = z.strictObject({
  type: z.literal("llm_metrics"),
  label: z.string(),
  request_id: z.string(),
  timestamp: z.number(),
  duration: z.number(),
  ttft: z.number(),
  cancelled: z.boolean(),
  completion_tokens: z.int(),
  prompt_tokens: z.int(),
  prompt_cached_tokens: z.int(),
  cache_creation_tokens: z.int().nullish(),
  reasoning_tokens: z.int().nullish(),
  total_tokens: z.int(),
  tokens_per_second: z.number(),
  speech_id: z.string().nullable().nullish(),
  metadata: MetadataSchema.nullable().nullish(),
});

/**
 * One speech-to-text request, measured by the session's stt node. A streaming STT reports one per
 * connection segment, with duration 0.
 */
export const STTMetricsSchema = z.strictObject({
  type: z.literal("stt_metrics"),
  label: z.string(),
  request_id: z.string(),
  timestamp: z.number(),
  duration: z.number(),
  audio_duration: z.number(),
  input_tokens: z.int().nullish(),
  output_tokens: z.int().nullish(),
  streamed: z.boolean(),
  acquire_time: z.number().nullish(),
  connection_reused: z.boolean().nullish(),
  metadata: MetadataSchema.nullable().nullish(),
});

/**
 * One text-to-speech request, measured by the session's tts node. One reply may produce several,
 * one per sentence segment.
 */
export const TTSMetricsSchema = z.strictObject({
  type: z.literal("tts_metrics"),
  label: z.string(),
  request_id: z.string(),
  timestamp: z.number(),
  ttfb: z.number(),
  duration: z.number(),
  audio_duration: z.number(),
  cancelled: z.boolean(),
  characters_count: z.int(),
  input_tokens: z.int().nullish(),
  output_tokens: z.int().nullish(),
  streamed: z.boolean(),
  acquire_time: z.number().nullish(),
  connection_reused: z.boolean().nullish(),
  segment_id: z.string().nullable().nullish(),
  speech_id: z.string().nullable().nullish(),
  metadata: MetadataSchema.nullable().nullish(),
});

/**
 * The voice activity detector's health, reported about once a second while it runs. Not a per-turn
 * measure.
 */
export const VADMetricsSchema = z.strictObject({
  type: z.literal("vad_metrics"),
  label: z.string(),
  timestamp: z.number(),
  idle_time: z.number(),
  inference_duration_total: z.number(),
  inference_count: z.int(),
  metadata: MetadataSchema.nullable().nullish(),
});

/** How long the session took to decide that the caller had finished. One per user turn. */
export const EOUMetricsSchema = z.strictObject({
  type: z.literal("eou_metrics"),
  timestamp: z.number(),
  end_of_utterance_delay: z.number(),
  transcription_delay: z.number(),
  on_user_turn_completed_delay: z.number(),
  speech_id: z.string().nullable().nullish(),
  metadata: MetadataSchema.nullable().nullish(),
});

/**
 * One prediction by the end-of-turn model. It listens to the audio and says whether the caller is
 * done.
 */
export const EOTInferenceMetricsSchema = z.strictObject({
  type: z.literal("eot_inference_metrics"),
  timestamp: z.number(),
  total_duration: z.number(),
  detection_delay: z.number(),
  prediction_duration: z.number(),
  num_requests: z.int().nullish(),
  metadata: MetadataSchema.nullable().nullish(),
});

/**
 * The interruption detector's latest inference and its running counts. Reported when the detector
 * runs, not per turn.
 */
export const InterruptionMetricsSchema = z.strictObject({
  type: z.literal("interruption_metrics"),
  timestamp: z.number(),
  total_duration: z.number(),
  prediction_duration: z.number(),
  detection_delay: z.number(),
  num_interruptions: z.int(),
  num_backchannels: z.int(),
  num_requests: z.int(),
  metadata: MetadataSchema.nullable().nullish(),
});

/** Of a realtime model's cached input, how much was audio, text or image. */
export const RealtimeCachedTokenDetailsSchema = z.strictObject({
  audio_tokens: z.int().nullish(),
  text_tokens: z.int().nullish(),
  image_tokens: z.int().nullish(),
});

/** What a realtime model read, by kind, with the cached part broken out. */
export const RealtimeInputTokenDetailsSchema = z.strictObject({
  audio_tokens: z.int().nullish(),
  text_tokens: z.int().nullish(),
  image_tokens: z.int().nullish(),
  cached_tokens: z.int().nullish(),
  cached_tokens_details: RealtimeCachedTokenDetailsSchema.nullable().nullish(),
});

/** What a realtime model produced, by kind. */
export const RealtimeOutputTokenDetailsSchema = z.strictObject({
  text_tokens: z.int().nullish(),
  audio_tokens: z.int().nullish(),
  image_tokens: z.int().nullish(),
});

/**
 * One response from a speech-to-speech model, which replaces STT, LLM and TTS at once. Pinecall's
 * default pipeline never emits it; a realtime provider would.
 */
export const RealtimeModelMetricsSchema = z.strictObject({
  type: z.literal("realtime_model_metrics"),
  label: z.string().nullish(),
  request_id: z.string(),
  timestamp: z.number(),
  duration: z.number().nullish(),
  session_duration: z.number().nullish(),
  ttft: z.number().nullish(),
  cancelled: z.boolean().nullish(),
  input_tokens: z.int().nullish(),
  output_tokens: z.int().nullish(),
  total_tokens: z.int().nullish(),
  tokens_per_second: z.number().nullish(),
  input_token_details: RealtimeInputTokenDetailsSchema,
  output_token_details: RealtimeOutputTokenDetailsSchema,
  acquire_time: z.number().nullish(),
  connection_reused: z.boolean().nullish(),
  metadata: MetadataSchema.nullable().nullish(),
});

/**
 * Timing of a video avatar worker, when one is in the chain. No Pinecall channel has one today;
 * carried because the library measures it.
 */
export const AvatarMetricsSchema = z.strictObject({
  type: z.literal("avatar_metrics"),
  timestamp: z.number(),
  playback_latency: z.number().nullish(),
  session_started_time: z.number().nullable().nullish(),
  avatar_joined_time: z.number().nullable().nullish(),
  metadata: MetadataSchema.nullable().nullish(),
});

/** Which model handled one leg of a turn. livekit's MetricsMetadata, as it sits on the ChatMessage. */
export const TurnMetadataSchema = z.strictObject({
  model_name: z.string().nullish(),
  model_provider: z.string().nullish(),
});

/**
 * What the session measured about the caller's turn. livekit stamps it on the user ChatMessage;
 * every field is optional, since a text session has no speech to time.
 */
export const UserTurnMetricsSchema = z.strictObject({
  started_speaking_at: z.number().nullish(),
  stopped_speaking_at: z.number().nullish(),
  transcription_delay: z.number().nullish(),
  end_of_turn_delay: z.number().nullish(),
  on_user_turn_completed_delay: z.number().nullish(),
  stt_metadata: TurnMetadataSchema.nullish(),
});

/**
 * What the session measured about the agent's reply. livekit stamps it on the assistant
 * ChatMessage; every field is optional, since a text session has no audio to time.
 */
export const AgentTurnMetricsSchema = z.strictObject({
  started_speaking_at: z.number().nullish(),
  stopped_speaking_at: z.number().nullish(),
  llm_node_ttft: z.number().nullish(),
  llm_node_tps: z.number().nullish(),
  llm_node_ttfs: z.number().nullish(),
  tts_node_ttfb: z.number().nullish(),
  playback_latency: z.number().nullish(),
  e2e_latency: z.number().nullish(),
  provider_request_ids: z.array(z.string()).nullish(),
  llm_metadata: TurnMetadataSchema.nullish(),
  tts_metadata: TurnMetadataSchema.nullish(),
});

/**
 * Everything one LLM consumed over the call. One row per provider and model, as livekit's usage
 * collector sums it.
 */
export const LLMModelUsageSchema = z.strictObject({
  type: z.literal("llm_usage"),
  provider: z.string(),
  model: z.string(),
  input_tokens: z.int().nullish(),
  input_cached_tokens: z.int().nullish(),
  input_cache_creation_tokens: z.int().nullish(),
  input_audio_tokens: z.int().nullish(),
  input_cached_audio_tokens: z.int().nullish(),
  input_text_tokens: z.int().nullish(),
  input_cached_text_tokens: z.int().nullish(),
  input_image_tokens: z.int().nullish(),
  input_cached_image_tokens: z.int().nullish(),
  output_tokens: z.int().nullish(),
  output_audio_tokens: z.int().nullish(),
  output_text_tokens: z.int().nullish(),
  output_reasoning_tokens: z.int().nullish(),
  session_duration: z.number().nullish(),
});

/** Everything one TTS consumed over the call. */
export const TTSModelUsageSchema = z.strictObject({
  type: z.literal("tts_usage"),
  provider: z.string(),
  model: z.string(),
  input_tokens: z.int().nullish(),
  output_tokens: z.int().nullish(),
  characters_count: z.int().nullish(),
  audio_duration: z.number().nullish(),
});

/** Everything one STT consumed over the call. */
export const STTModelUsageSchema = z.strictObject({
  type: z.literal("stt_usage"),
  provider: z.string(),
  model: z.string(),
  input_tokens: z.int().nullish(),
  output_tokens: z.int().nullish(),
  audio_duration: z.number().nullish(),
});

/** How often the interruption detector was asked over the call. */
export const InterruptionModelUsageSchema = z.strictObject({
  type: z.literal("interruption_usage"),
  provider: z.string(),
  model: z.string(),
  total_requests: z.int().nullish(),
});

/** How often the end-of-turn model was asked over the call. */
export const EOTModelUsageSchema = z.strictObject({
  type: z.literal("eot_usage"),
  provider: z.string(),
  model: z.string(),
  total_requests: z.int().nullish(),
});

/** One usage row, told apart by its type tag. */
export const ModelUsageSchema = z.discriminatedUnion("type", [LLMModelUsageSchema, TTSModelUsageSchema, STTModelUsageSchema, InterruptionModelUsageSchema, EOTModelUsageSchema]);
