/** The log's doors: a page of entries, the call list, the box's events, a contact's thread. */

import { z } from "zod";
import {
  ChannelSchema,
  ContactSchema,
  CostSchema,
  DirectionSchema,
  EndReasonSchema,
  EnvSchema,
} from "./defs.js";
import { EntrySchema } from "./envelope.js";
import { AttentionStateSchema, CallStatusSchema } from "./state.js";

/** One page of a log: what this reader may see, whether the log is open, and where to resume. */
export const LogPageSchema = z.strictObject({
  entries: z.array(EntrySchema),
  live: z.boolean(),
  next: z.int().nullable(),
});

/**
 * One call's call.score as a list draws it: how many judges held of how many answered, and why the
 * first one that broke did.
 */
export const SessionScoreSchema = z.strictObject({
  held: z.int(),
  judged: z.int(),
  passed: z.boolean(),
  reason: z.string().nullable(),
});

/**
 * escalated: a person took part — a transfer, a supervisor taking the line, saying something, or
 * ending the call. low_score: a judge answered broken. promise: the promises judge found the agent
 * committing the business to something no tool call records.
 */
export const SessionFlagSchema = z.enum(["escalated", "low_score", "promise"]);

export type SessionFlag = z.infer<typeof SessionFlagSchema>;

/** One call as a list draws it: which call, how far the log got, and the state's own fields. */
export const SessionLineSchema = z.strictObject({
  call: z.string(),
  agent: z.string(),
  live: z.boolean(),
  last_seq: z.int(),
  status: CallStatusSchema,
  channel: ChannelSchema.nullable(),
  direction: DirectionSchema.nullable(),
  from: z.string().nullable(),
  to: z.string().nullable(),
  caller: ContactSchema.nullable(),
  started_at: z.number().nullable(),
  ended_at: z.number().nullable(),
  end_reason: EndReasonSchema.nullable(),
  outcome: z.string().nullable(),
  cost: CostSchema.nullable(),
  score: SessionScoreSchema.nullable().nullish(),
  flags: z.array(SessionFlagSchema).nullish(),
  attention: AttentionStateSchema.nullable().nullish(),
});

export type SessionLine = z.infer<typeof SessionLineSchema>;

/**
 * One frame of GET /v1/ops/events: an entry of some org's floor, whose floor it is, and the world
 * of its call (null on an agent's own entries, which serve both). The operator's stream, every
 * org of the box at once.
 */
export const BoxEventSchema = z.strictObject({
  org: z.string(),
  env: EnvSchema.nullable(),
  entry: EntrySchema,
});

export type BoxEvent = z.infer<typeof BoxEventSchema>;

/**
 * GET /v1/agents/{slug}/sessions and GET /v1/sessions: the calls that match, newest first, a page
 * at a time.
 */
export const SessionListSchema = z.strictObject({
  calls: z.array(SessionLineSchema),
  total: z.int().nullable().nullish(),
  next: z.string().nullable().nullish(),
});

