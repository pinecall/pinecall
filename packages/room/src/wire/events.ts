/** The events of what happens during a call: talk, tools, the desk, memory, errors. */

import { z } from "zod";
import {
  ChannelSchema,
  DevVerbSchema,
  DocSourceSchema,
  EnvSchema,
  MemoryOpSchema,
  ProjectionSchema,
  ScoreVerdictSchema,
  SupervisorSchema,
  TransferModeSchema,
  UserStateSchema,
} from "./defs.js";
import { UserTurnMetricsSchema } from "./metrics.js";
import { StateSchema } from "./state.js";

/**
 * An ask for a person settled: a supervisor took the line, or the wait ran out and the agent has
 * the caller back.
 */
export const AttentionAnsweredSchema = z.strictObject({
  ok: z.boolean(),
  by: SupervisorSchema.nullable(),
  error: z.string().nullish(),
});

/**
 * The agent asked for a person: the caller is on hold and waits for a supervisor to take the line.
 * What a supervisor's console and phone are notified by.
 */
export const AttentionRequestedSchema = z.strictObject({
  reason: z.string(),
  wait_s: z.number(),
});

/**
 * Where in the call's own log a judgment is about. A reader who disagrees with a verdict opens the
 * log at those lines.
 */
export const JudgmentEvidenceSchema = z.strictObject({
  seqs: z.array(z.int()),
  said: z.string().nullish(),
});

/**
 * One judge's answer about one call: the question it was asked, the word it answered and the
 * sentence that says why.
 */
export const JudgmentSchema = z.strictObject({
  name: z.string(),
  verdict: ScoreVerdictSchema,
  criteria: z.string(),
  reason: z.string(),
  evidence: JudgmentEvidenceSchema,
});

/** One code, taken or expired. */
export const CodeClaimedSchema = z.strictObject({
  code: z.string(),
  call: z.string().nullable(),
});

/** One code, waiting for the call that keys it. */
export const CodeIssuedSchema = z.strictObject({
  code: z.string(),
  env: EnvSchema,
  expires_at: z.number(),
  log: ProjectionSchema,
});

/** The caller did not say yes, or the request lapsed. The tool does not run; the model is told. */
export const ConfirmDeclinedSchema = z.strictObject({
  tool: z.string(),
  call_id: z.string(),
  audience: z.string(),
  said: z.string().nullish(),
  reason: z.enum(["no", "timeout", "changed", "cancelled"]),
});

/**
 * The caller said yes. The platform minted a one-shot token bound to the audience and the tool now
 * runs. The token itself never enters the log.
 */
export const ConfirmGrantedSchema = z.strictObject({
  tool: z.string(),
  call_id: z.string(),
  audience: z.string(),
  said: z.string(),
  ttl_s: z.int(),
});

/**
 * A tool with confirm set is about to run and the platform is asking the caller. The agent reads
 * the phrase; nothing runs until confirm.granted.
 */
export const ConfirmRequestSchema = z.strictObject({
  tool: z.string(),
  call_id: z.string(),
  arguments: z.record(z.string(), z.unknown()),
  audience: z.string(),
  phrase: z.string(),
  ttl_s: z.int(),
});

/**
 * The gateway refused a call, a written turn or a register because one of the org's quotas ran
 * out. Written into the agent's own log, which is the org's, before the door says no.
 */
export const CreditsExhaustedSchema = z.strictObject({
  org: z.string(),
  quota: z.enum(["minutes", "messages", "agents", "concurrent_calls", "memory_facts", "knowledge_chunks", "numbers", "seats", "llm_tokens"]),
  used: z.number(),
  limit: z.int(),
});

/**
 * A line the app wrote into the log with call.log. The platform never reads it; the console shows
 * it and evals may.
 */
export const CustomSchema = z.strictObject({
  name: z.string(),
  data: z.record(z.string(), z.unknown()),
});

/** One ask of the process in the agent's directory, on a console's behalf. */
export const DevRequestSchema = z.strictObject({
  id: z.string(),
  verb: DevVerbSchema,
  data: z.record(z.string(), z.unknown()),
});

/**
 * What retrieval put in front of the model for this turn. An answer can be traced back to its
 * chunks.
 */
export const DocsSourcesSchema = z.strictObject({
  query: z.string(),
  sources: z.array(DocSourceSchema),
  took_ms: z.number(),
  speech_id: z.string().nullish(),
});

/** One tone the caller keyed. */
export const DtmfReceivedSchema = z.strictObject({
  digit: z.enum(["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "*", "#"]),
  code: z.int(),
});

/**
 * Something went wrong. Inside a call it says what failed; outside a call it says which command
 * the gateway refused.
 */
export const ErrorEventSchema = z.strictObject({
  code: z.string(),
  message: z.string(),
  command: z.string().nullish(),
  id: z.string().nullish(),
  recoverable: z.boolean(),
});

/**
 * The gateway refused to open a call because every worker of the fleet was full. Written into the
 * agent's own log, which is the org's, before the door says no — the caller was offered a call
 * back instead of a room.
 */
export const FleetFullSchema = z.strictObject({
  channel: ChannelSchema,
  workers: z.int(),
  active: z.int(),
});

/**
 * The replay is done: everything up to seq has been sent and what follows is live. Never stored;
 * sent to the reader.
 */
export const LogCaughtUpSchema = z.strictObject({
  seq: z.int(),
});

/**
 * This reader missed a stretch: it reconnected too late for the store, or fell behind and the
 * fanout dropped ephemeral entries. When the platform has a snapshot, it is here so the reader can
 * catch up in one step. Never stored; sent to the reader.
 */
export const LogGapSchema = z.strictObject({
  from_seq: z.int(),
  to_seq: z.int(),
  snapshot: StateSchema.nullable(),
});

/**
 * What memory did for this turn or at hangup: a recall before the reply, a remember after the
 * call, a forget on request.
 */
export const MemoryOpsSchema = z.strictObject({
  ops: z.array(MemoryOpSchema),
  speech_id: z.string().nullish(),
});

/** One waiting message, off the queue. */
export const MessageTakenSchema = z.strictObject({
  message_id: z.string(),
  call: z.string().nullable(),
});

/** One message, kept until somebody can answer it. */
export const MessageWaitingSchema = z.strictObject({
  channel: ChannelSchema,
  env: EnvSchema,
  number: z.string(),
  phone_number_id: z.string(),
  from: z.string(),
  name: z.string().nullable(),
  message_id: z.string(),
  text: z.string(),
  received_at: z.number(),
});

/** The answer to ping. Ephemeral: it proves the socket is alive and says nothing else. */
export const PongSchema = z.strictObject({
  ts: z.number(),
});

/**
 * A block of the prompt was rewritten. The text stays out of the log; its hash and length let two
 * states be compared.
 */
export const PromptChangedSchema = z.strictObject({
  name: z.string(),
  hash: z.string(),
  chars: z.int(),
});

/** A tool call's result changed the state. */
export const StateCauseToolSchema = z.strictObject({
  kind: z.literal("tool"),
  tool: z.string(),
  call_id: z.string(),
});

/** A fact from outside changed the state: the app's handler for an event.received moved a field. */
export const StateCauseEventSchema = z.strictObject({
  kind: z.literal("event"),
  name: z.string(),
  seq: z.int(),
});

/** What changed the state: a tool's result, or a fact from outside. Told apart by kind. */
export const StateCauseSchema = z.discriminatedUnion("kind", [StateCauseToolSchema, StateCauseEventSchema]);

/**
 * The app's declared state changed. A tool's result or an outside fact caused it, and the cause
 * says which; the whole state travels so a reader never needs the previous entry.
 */
export const StateChangedSchema = z.strictObject({
  state: z.record(z.string(), z.unknown()),
  changed: z.array(z.string()),
  cause: StateCauseSchema.nullish(),
});

/** A supervisor hung up the call. call.ended follows with reason supervisor_ended. */
export const SupervisorEndedSchema = z.strictObject({
  by: SupervisorSchema,
  reason: z.string().nullish(),
});

/** The supervisor gave the line back; the agent resumes with the history intact. */
export const SupervisorReleasedSchema = z.strictObject({
  by: SupervisorSchema,
});

/** A supervisor made the agent say this to the caller. */
export const SupervisorSaidSchema = z.strictObject({
  by: SupervisorSchema,
  text: z.string(),
});

/** A supervisor took the line; the agent is quiet until supervisor.released. */
export const SupervisorTookOverSchema = z.strictObject({
  by: SupervisorSchema,
});

/** A supervisor asked for a transfer. call.transferred says how it went. */
export const SupervisorTransferredSchema = z.strictObject({
  by: SupervisorSchema,
  to: z.string(),
  mode: TransferModeSchema.nullable().nullish(),
});

/** A supervisor told the agent something the caller never heard. */
export const SupervisorWhisperedSchema = z.strictObject({
  by: SupervisorSchema,
  text: z.string(),
});

/**
 * The model called a tool. The platform sends this to the app and the app's method runs in the
 * app's own process; tool.result closes it.
 */
export const ToolCallSchema = z.strictObject({
  call_id: z.string(),
  name: z.string(),
  arguments: z.record(z.string(), z.unknown()),
  speech_id: z.string().nullish(),
});

/** The tools the model can see changed. The app's state moved and each tool's when was recomputed. */
export const ToolsChangedSchema = z.strictObject({
  visible: z.array(z.string()),
});

/**
 * The caller's turn is over and this is what they said. With it, everything the session measured
 * about the turn.
 */
export const UserTurnEndedSchema = z.strictObject({
  speech_id: z.string(),
  item_id: z.string().nullish(),
  text: z.string(),
  language: z.string().nullish(),
  transcript_confidence: z.number().nullish(),
  metrics: UserTurnMetricsSchema,
});

/** The caller's state changed, in the session's own words. */
export const UserStateChangedSchema = z.strictObject({
  state: UserStateSchema,
});

/**
 * Words from the caller as the recognizer hears them. Interim while final is false; the final one
 * becomes turn.user. Interim entries are ephemeral.
 */
export const UserTranscriptSchema = z.strictObject({
  text: z.string(),
  final: z.boolean(),
  language: z.string().nullish(),
  confidence: z.number().nullish(),
});
