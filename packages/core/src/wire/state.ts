/** What a log reduces to: the call, its turns, its tools, its people, its metrics. */

import { z } from "zod";
import {
  AgentStateSchema,
  ChannelSchema,
  ContactSchema,
  CostSchema,
  DirectionSchema,
  DocSourceSchema,
  EndReasonSchema,
  EventSourceSchema,
  MemoryOpSchema,
  ParticipantKindSchema,
  RouteSchema,
  SupervisorSchema,
  TransferModeSchema,
  UserStateSchema,
} from "./defs.js";
import {
  AgentTurnMetricsSchema,
  AvatarMetricsSchema,
  EOTInferenceMetricsSchema,
  EOUMetricsSchema,
  InterruptionMetricsSchema,
  LLMMetricsSchema,
  ModelUsageSchema,
  RealtimeModelMetricsSchema,
  STTMetricsSchema,
  TTSMetricsSchema,
  UserTurnMetricsSchema,
  VADMetricsSchema,
} from "./metrics.js";

/**
 * Where the call is in its life. idle before any call.* entry, which is what an agent's own log
 * looks like.
 */
export const CallStatusSchema = z.enum(["idle", "ringing", "dialing", "active", "ended"]);

/** One finished turn of the caller, with what the session measured about it. */
export const UserTurnSchema = z.strictObject({
  role: z.literal("user"),
  speech_id: z.string(),
  item_id: z.string().nullish(),
  text: z.string(),
  language: z.string().nullish(),
  transcript_confidence: z.number().nullish(),
  metrics: UserTurnMetricsSchema,
});

/** One finished reply of the agent, with what the session measured about it. */
export const AgentTurnSchema = z.strictObject({
  role: z.literal("agent"),
  speech_id: z.string(),
  item_id: z.string().nullish(),
  text: z.string(),
  interrupted: z.boolean(),
  metrics: AgentTurnMetricsSchema,
});

/** One turn of either side, told apart by role. */
export const TurnSchema = z.discriminatedUnion("role", [UserTurnSchema, AgentTurnSchema]);

export type Turn = z.infer<typeof TurnSchema>;

/**
 * Every raw metric block of the call, by kind, in the order it arrived. The turns hold the join;
 * this holds the measurements.
 */
export const CollectedMetricsSchema = z.strictObject({
  llm: z.array(LLMMetricsSchema),
  stt: z.array(STTMetricsSchema),
  tts: z.array(TTSMetricsSchema),
  vad: z.array(VADMetricsSchema),
  eou: z.array(EOUMetricsSchema),
  eot: z.array(EOTInferenceMetricsSchema),
  interruption: z.array(InterruptionMetricsSchema),
  realtime: z.array(RealtimeModelMetricsSchema),
  avatar: z.array(AvatarMetricsSchema),
});

export type CollectedMetrics = z.infer<typeof CollectedMetricsSchema>;

/** One tool call and, once the app answered, its result. */
export const ToolRunSchema = z.strictObject({
  call_id: z.string(),
  name: z.string(),
  arguments: z.record(z.string(), z.unknown()),
  speech_id: z.string().nullish(),
  status: z.enum(["running", "done", "failed"]),
  output: z.unknown().nullish(),
  error: z.string().nullish(),
  summary: z.string().nullish(),
  duration_s: z.number().nullish(),
  seq: z.int(),
});

export type ToolRun = z.infer<typeof ToolRunSchema>;

/** What is known about one block of the prompt without storing its text. */
export const PromptBlockStateSchema = z.strictObject({
  hash: z.string(),
  chars: z.int(),
  seq: z.int(),
});

/**
 * Every block the app has written, by name, without its text. The history between the static and
 * the dynamic blocks is the turns.
 */
export const PromptStateSchema = z.record(z.string(), PromptBlockStateSchema);

export type PromptState = z.infer<typeof PromptStateSchema>;

/** One confirmation the platform asked for, and how it went. */
export const ConfirmSchema = z.strictObject({
  tool: z.string(),
  call_id: z.string(),
  audience: z.string(),
  phrase: z.string(),
  status: z.enum(["pending", "granted", "declined"]),
  said: z.string().nullish(),
  reason: z.string().nullish(),
});

export type Confirm = z.infer<typeof ConfirmSchema>;

/** Whether a supervisor holds the line right now. */
export const HandoffSchema = z.strictObject({
  active: z.boolean(),
  by: SupervisorSchema.nullable(),
});

/** The transfer in flight or the one that happened. */
export const TransferStateSchema = z.strictObject({
  to: z.string(),
  mode: TransferModeSchema.nullable().nullish(),
  status: z.enum(["requested", "done", "failed"]),
  by: z.enum(["agent", "supervisor"]),
});

/** The agent's last ask for a person, from attention.requested until attention.answered settles it. */
export const AttentionStateSchema = z.strictObject({
  reason: z.string(),
  wait_s: z.number(),
  status: z.enum(["open", "answered", "lapsed"]),
  asked_at: z.number(),
  by: SupervisorSchema.nullable(),
});

export type AttentionState = z.infer<typeof AttentionStateSchema>;

/** The words on screen right now: interim transcripts that a finished turn clears. */
export const LiveTranscriptSchema = z.strictObject({
  user: z.string().nullable(),
  agent: z.string().nullable(),
});

export type LiveTranscript = z.infer<typeof LiveTranscriptSchema>;

/** A stretch of seqs this reader never saw. */
export const GapSchema = z.strictObject({
  from_seq: z.int(),
  to_seq: z.int(),
});

/** An error entry, kept so the console can show what went wrong and when. */
export const LoggedErrorSchema = z.strictObject({
  seq: z.int(),
  code: z.string(),
  message: z.string(),
});

/** One participant in the room right now, as the room reported them when they joined. */
export const ParticipantSchema = z.strictObject({
  identity: z.string(),
  kind: ParticipantKindSchema,
  name: z.string().nullish(),
  joined_at: z.number(),
  speaking: z.boolean(),
  attributes: z.record(z.string(), z.unknown()),
});

export type Participant = z.infer<typeof ParticipantSchema>;

/** The LiveKit room the call lives in, and who is in it right now. */
export const RoomSchema = z.strictObject({
  name: z.string(),
  sid: z.string(),
  participants: z.array(ParticipantSchema),
  caller: z.string().nullable(),
});

export type Room = z.infer<typeof RoomSchema>;

/**
 * One fact that reached the agent from outside the conversation, kept by name and origin. Its data
 * is in the log at that seq.
 */
export const ReceivedEventSchema = z.strictObject({
  seq: z.int(),
  name: z.string(),
  source: EventSourceSchema,
  identity: z.string().nullish(),
});

/** A line the app wrote into the log with call.log. */
export const CustomNoteSchema = z.strictObject({
  seq: z.int(),
  name: z.string(),
  data: z.record(z.string(), z.unknown()),
});

export type CustomNote = z.infer<typeof CustomNoteSchema>;

/** The whole of what a log says, at the seq it was read to. */
export const StateSchema = z.strictObject({
  seq: z.int(),
  agent: z.string(),
  call: z.string().nullable(),
  status: CallStatusSchema,
  channel: ChannelSchema.nullable(),
  direction: DirectionSchema.nullable(),
  from: z.string().nullable(),
  to: z.string().nullable(),
  caller: ContactSchema.nullable(),
  room: RoomSchema.nullable(),
  started_at: z.number().nullable(),
  ended_at: z.number().nullable(),
  end_reason: EndReasonSchema.nullable(),
  outcome: z.string().nullable(),
  user_state: UserStateSchema.nullable(),
  agent_state: AgentStateSchema.nullable(),
  live: LiveTranscriptSchema,
  turns: z.array(TurnSchema),
  metrics: CollectedMetricsSchema,
  tools: z.array(ToolRunSchema),
  app_state: z.record(z.string(), z.unknown()),
  events: z.array(ReceivedEventSchema),
  prompt: PromptStateSchema,
  tools_visible: z.array(z.string()),
  confirms: z.array(ConfirmSchema),
  memory: z.array(MemoryOpSchema),
  sources: z.array(DocSourceSchema),
  handoff: HandoffSchema,
  held: z.boolean(),
  muted: z.boolean(),
  transfer: TransferStateSchema.nullable(),
  attention: AttentionStateSchema.nullable().nullish(),
  usage: z.array(ModelUsageSchema),
  cost: CostSchema.nullable(),
  routes: z.array(RouteSchema),
  gaps: z.array(GapSchema),
  errors: z.array(LoggedErrorSchema),
  custom: z.array(CustomNoteSchema),
});

export type State = z.infer<typeof StateSchema>;
