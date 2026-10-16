/** The events of a call's life and of the agent that holds it. */

import { z } from "zod";
import {
  AgentStateSchema,
  ChannelSchema,
  ContactSchema,
  CostSchema,
  DirectionSchema,
  EndedBySchema,
  EndReasonSchema,
  EnvSchema,
  RouteSchema,
  TransferModeSchema,
} from "./defs.js";
import { JudgmentSchema } from "./events.js";
import { AgentTurnMetricsSchema, ModelUsageSchema } from "./metrics.js";

/**
 * The gateway applied an agent.configure. Live calls keep their session; the next call starts with
 * the new config.
 */
export const AgentConfiguredSchema = z.strictObject({
  changed: z.array(z.string()),
});

/** One socket stopped holding the agent. */
export const AgentDetachedSchema = z.strictObject({
  app: z.string(),
  env: EnvSchema,
  left: z.boolean(),
});

/** One socket let go of its calls without cutting them. */
export const AgentDrainingSchema = z.strictObject({
  app: z.string(),
  env: EnvSchema,
  handed: z.int(),
  parked: z.int(),
});

/**
 * The gateway accepted an agent.register: this socket now speaks for the agent and answers its
 * routes. Many sockets may hold one agent at once — a new call takes the newest of them, unless
 * the caller names one by its `app` id.
 */
export const AgentRegisteredSchema = z.strictObject({
  routes: z.array(RouteSchema),
  app: z.string(),
  sdk: z.string().nullish(),
  env: EnvSchema.nullish(),
});

/** The agent's state changed, in the session's own words. */
export const AgentStateChangedSchema = z.strictObject({
  state: AgentStateSchema,
});

/**
 * One delta of the reply the agent is giving, never the reply so far: in a voice call one word, as
 * the voice plays it, with the seconds it was aligned to; in a written call one model token. The
 * reply so far is every delta of the same speech_id since the last turn.agent, joined; turn.agent
 * carries the whole reply and closes it. Interim entries are ephemeral.
 */
export const AgentTranscriptSchema = z.strictObject({
  speech_id: z.string(),
  text: z.string(),
  final: z.boolean(),
  start: z.number().nullish(),
  end: z.number().nullish(),
});

/**
 * Media is up: the caller and the agent can hear each other, or the text session is open.
 * Everything the agent says and hears comes after this.
 */
export const CallStartedSchema = z.strictObject({
  channel: ChannelSchema,
  direction: DirectionSchema,
  from: z.string(),
  to: z.string(),
  run: z.string().nullable().nullish(),
  persona: z.string().nullable().nullish(),
  accepts_when: z.string().nullable().nullish(),
  declines_when: z.string().nullable().nullish(),
  caller: ContactSchema.nullable(),
  started_at: z.number(),
  env: EnvSchema.nullish(),
});

/** A call changed hands without ending. */
export const CallAttachedSchema = z.strictObject({
  app: z.string(),
  started: CallStartedSchema,
  state: z.record(z.string(), z.unknown()),
  seq: z.int(),
  claimed: z.string().nullable().nullish(),
});

/** The call was bound to a page's code. */
export const CallClaimedSchema = z.strictObject({
  code: z.string(),
  via: z.enum(["keypad", "agent"]),
});

/**
 * The platform is placing an outbound call and the far end has not answered yet. The first entry
 * of an outbound call's log.
 */
export const CallDialingSchema = z.strictObject({
  channel: ChannelSchema,
  from: z.string(),
  to: z.string(),
  run: z.string().nullable().nullish(),
  caller: ContactSchema.nullable(),
  external_id: z.string().nullish(),
  asked_by: z.string().nullish(),
});

/** The call is over. Nothing about the conversation follows; call.summary still does. */
export const CallEndedSchema = z.strictObject({
  reason: EndReasonSchema,
  ended_by: EndedBySchema,
  ended_at: z.number(),
  duration_s: z.number(),
});

/**
 * The line's hold and mute flags after one of them changed. Both are stated so a reader never has
 * to remember the other.
 */
export const CallLineSchema = z.strictObject({
  held: z.boolean(),
  muted: z.boolean(),
});

/**
 * An inbound call is offered to this agent and has not been answered yet. The first entry of an
 * inbound call's log.
 */
export const CallRingingSchema = z.strictObject({
  channel: ChannelSchema,
  from: z.string(),
  to: z.string(),
  route: RouteSchema,
  run: z.string().nullable().nullish(),
  caller: ContactSchema.nullable(),
  external_id: z.string().nullish(),
});

/**
 * The last entry of a call: what the judges said about it at hang-up, one row per judge. Written
 * after call.summary, and the entry the log seals on.
 */
export const CallScoreSchema = z.strictObject({
  passed: z.boolean().nullish(),
  not_judged: z.string().nullish(),
  judges: z.array(JudgmentSchema),
  panel: z.array(z.string()).nullish(),
  judge_calls: z.int(),
  judge_cost_usd: z.number().nullish(),
});

/**
 * What the call was about, how it went, what it consumed and what that cost. Written after
 * call.ended, once memory and pricing are done; call.score follows it and seals the log.
 */
export const CallSummarySchema = z.strictObject({
  reason: EndReasonSchema,
  outcome: z.string(),
  duration_s: z.number(),
  turns: z.int(),
  usage: z.array(ModelUsageSchema),
  cost: CostSchema,
  recording: z.string().nullish(),
});

/** A transfer asked for by the agent or a supervisor finished, one way or the other. */
export const CallTransferredSchema = z.strictObject({
  to: z.string(),
  mode: TransferModeSchema.nullable().nullish(),
  ok: z.boolean(),
  error: z.string().nullish(),
});

/**
 * Somebody asked to be called back: a phone caller the overflow agent answered, a web visitor who
 * left a number at the widget, or a caller who asked the agent for one (call.callback). Written
 * into the agent's own log; the tenant's app reads it and places the call.
 */
export const CallbackRequestedSchema = z.strictObject({
  channel: ChannelSchema,
  number: z.string(),
  via: z.enum(["overflow", "widget", "agent"]),
  call: z.string().nullable(),
  when: z.string().nullish(),
  note: z.string().nullish(),
  contact: ContactSchema.nullable(),
});

/**
 * The agent's reply is over and this is what was said. With it, everything the session measured
 * about the reply.
 */
export const AgentTurnEndedSchema = z.strictObject({
  speech_id: z.string(),
  item_id: z.string().nullish(),
  text: z.string(),
  interrupted: z.boolean(),
  metrics: AgentTurnMetricsSchema,
});
