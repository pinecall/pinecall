/** The read doors the CLI answers from: calls, apps, the line, settings, the lexicon, voices, judges. */

import { z } from "zod";
import {
  DocsConfigSchema,
  EndOfTurnSchema,
  GreetingConfigSchema,
  HangupConfigSchema,
  MemoryConfigSchema,
  PronunciationSchema,
  TurnConfigSchema,
} from "./agent-config.js";
import {
  ChannelSchema,
  ContactSchema,
  CostSchema,
  DirectionSchema,
  EndReasonSchema,
  EnvSchema,
} from "./defs.js";
import { JudgmentSchema } from "./events.js";
import { AttentionStateSchema, CallStatusSchema } from "./state.js";

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

/** One corner of a world holding an agent: the member whose it is, named so a person can read it. */
export const LineHolderSchema = z.strictObject({
  holder: z.string().nullable(),
  name: z.string().nullable(),
});

/**
 * One app connected to the gateway right now: one process on one machine, holding one or more
 * agents in one world.
 */
export const AppProcessSchema = z.strictObject({
  app: z.string(),
  agents: z.array(z.string()),
  env: EnvSchema,
  host: z.string().nullable(),
  address: z.string().nullable(),
  sdk: z.string().nullable(),
  holder: LineHolderSchema.nullable(),
  connected_at: z.number(),
});

export type AppProcess = z.infer<typeof AppProcessSchema>;

/**
 * GET /v1/apps: every app connected in the request's world that this key may see — its own
 * corner's and the org's, every corner's with `team`.
 */
export const AppListSchema = z.strictObject({
  apps: z.array(AppProcessSchema),
});

export type AppList = z.infer<typeof AppListSchema>;

/**
 * POST /v1/apps/{app}/stop, the answer: the socket was closed with the stop code, and the app
 * exits rather than reconnect.
 */
export const AppStoppedSchema = z.strictObject({
  app: z.string(),
  stopped: z.boolean(),
});

export type AppStopped = z.infer<typeof AppStoppedSchema>;

/**
 * POST /v1/agents/{slug}/kill, an admin's: every app holding the agent in the env let go of it and
 * kept its other agents. Nothing is erased; an app that declares it again holds it again.
 */
export const KilledAgentSchema = z.strictObject({
  agent: z.string(),
  envs: z.array(z.enum(["sandbox", "production"])),
  apps: z.array(z.string()),
});

export type KilledAgent = z.infer<typeof KilledAgentSchema>;

/**
 * GET /v1/agents/{slug}/line: whose terminal a call that RINGS at this agent's doors lands in. An
 * org shares one sandbox number, so it rings in one place and which one is claimed.
 */
export const TheLineSchema = z.strictObject({
  agent: z.string(),
  env: EnvSchema,
  held: z.boolean(),
  holding: LineHolderSchema.nullable().nullish(),
  yours: z.boolean(),
  waiting: z.array(LineHolderSchema),
  calling: z.array(z.string()),
});

export type TheLine = z.infer<typeof TheLineSchema>;

/**
 * An agent's settings: what the org set, per world and per corner. Every field is optional; one
 * left out is not set, and the runtime's own default stands for it.
 */
export const TuningBodySchema = z.strictObject({
  voice: z.string().nullish(),
  tts: z.string().nullish(),
  tts_model: z.string().nullish(),
  stt: z.string().nullish(),
  llm: z.string().nullish(),
  /** The model's temperature, in its vendor's range. */
  temperature: z.number().nullish(),
  /** Who says the caller's turn is over: `stt`, `livekit` or `smart-turn`. */
  end_of_turn: EndOfTurnSchema.nullish(),
  /** A class of each stage's plugin other than its default, and its keyword arguments: the org's own key alone runs them. */
  llm_builds: z.string().nullish(),
  llm_options: z.record(z.string(), z.unknown()).nullish(),
  /** The model a voice call runs on alone, `vendor/model`, hearing and speaking itself; its options on the org's own key. A written call runs on `llm`. */
  realtime: z.string().nullish(),
  realtime_options: z.record(z.string(), z.unknown()).nullish(),
  stt_builds: z.string().nullish(),
  stt_options: z.record(z.string(), z.unknown()).nullish(),
  tts_builds: z.string().nullish(),
  tts_options: z.record(z.string(), z.unknown()).nullish(),
  /** The model the agent's calls are judged on, `vendor/model`; on the org's own key its evals are never billed. */
  judge: z.string().nullish(),
  judge_builds: z.string().nullish(),
  judge_options: z.record(z.string(), z.unknown()).nullish(),
  /** A language tag (`en`, `pt-BR`) the voice and the ears are set to; unset, each vendor's own. */
  language: z.string().nullish(),
  greeting: GreetingConfigSchema.nullish(),
  hangup: HangupConfigSchema.nullish(),
  turn: TurnConfigSchema.nullish(),
  memory: MemoryConfigSchema.nullish(),
  record: z.boolean().nullish(),
  max_duration_s: z.int().nullish(),
  knowledge: z.string().nullish(),
  bases: z.array(DocsConfigSchema).nullish(),
});

export type TuningBody = z.infer<typeof TuningBodySchema>;

/**
 * One kept version of an agent's tuning: whose corner, which version, who set it and when, and
 * what it says.
 */
export const TuningRowSchema = z.strictObject({
  holder: z.string(),
  version: z.int(),
  author: z.string(),
  note: z.string().nullable(),
  set_at: z.number(),
  config: TuningBodySchema,
});

export type TuningRow = z.infer<typeof TuningRowSchema>;

/**
 * GET /v1/agents/{slug}/settings: the agent's tuning as this key sees it — its own corner's, the
 * team's and production's, each corner's own newest row, or null when that corner set nothing.
 */
export const TuningAnswerSchema = z.strictObject({
  world: EnvSchema,
  yours: TuningRowSchema.nullable(),
  team: TuningRowSchema.nullable(),
  production: TuningRowSchema.nullable(),
  /** The settings the class holding the agent declares itself, by the declaration's names: each wins over these. */
  fixed: z.array(z.string()),
});

export type TuningAnswer = z.infer<typeof TuningAnswerSchema>;

/** GET /v1/agents/{slug}/settings/history: one corner's versions, newest first. */
export const TuningHistorySchema = z.strictObject({
  world: EnvSchema,
  holder: z.string(),
  rows: z.array(TuningRowSchema),
});

export type TuningHistory = z.infer<typeof TuningHistorySchema>;

/**
 * GET /v1/agents/{slug}/settings/diff: what this key's corner reads against another corner's
 * newest, and which fields differ.
 */
export const TuningDiffSchema = z.strictObject({
  ours: TuningRowSchema.nullable(),
  theirs: TuningRowSchema.nullable(),
  changed: z.array(z.string()),
});

export type TuningDiff = z.infer<typeof TuningDiffSchema>;

/**
 * An agent's lexicon: how the voice says the words it would get wrong, and the words the ears must
 * know: the agent's says and hears, unless its class declares them.
 */
export const LexiconBodySchema = z.strictObject({
  said: z.array(PronunciationSchema),
  heard: z.array(z.string()),
});

export type LexiconBody = z.infer<typeof LexiconBodySchema>;

/** One kept version of an agent's lexicon. */
export const LexiconRowSchema = z.strictObject({
  holder: z.string(),
  version: z.int(),
  author: z.string(),
  note: z.string().nullable(),
  set_at: z.number(),
  lexicon: LexiconBodySchema,
});

export type LexiconRow = z.infer<typeof LexiconRowSchema>;

/**
 * GET /v1/agents/{slug}/lexicon: the agent's words as this key sees them — its own corner's, the
 * team's and production's, each corner's own newest, or null.
 */
export const LexiconAnswerSchema = z.strictObject({
  world: EnvSchema,
  yours: LexiconRowSchema.nullable(),
  team: LexiconRowSchema.nullable(),
  production: LexiconRowSchema.nullable(),
  /** Which of `says` and `hears` the class holding the agent declares itself. */
  fixed: z.array(z.string()),
});

export type LexiconAnswer = z.infer<typeof LexiconAnswerSchema>;

/** GET /v1/agents/{slug}/lexicon/history: one corner's versions, newest first. */
export const LexiconHistorySchema = z.strictObject({
  world: EnvSchema,
  holder: z.string(),
  rows: z.array(LexiconRowSchema),
});

export type LexiconHistory = z.infer<typeof LexiconHistorySchema>;

/**
 * One voice a picker offers, as GET /v1/voices lists it: the id the `voice` setting takes, and
 * what a person chooses by. `country` and `accent` are the vendor's own words (`ES` is Spain, `MX`
 * Mexico), empty when the vendor said none.
 */
export const ListedVoiceSchema = z.strictObject({
  id: z.string(),
  name: z.string(),
  language: z.string(),
  description: z.string(),
  gender: z.string(),
  country: z.string(),
  accent: z.string(),
});

/**
 * GET /v1/voices?tts=&language=: a voice vendor's own voices in one language, in the vendor's
 * order.
 */
export const VoicesListedSchema = z.strictObject({
  tts: z.string(),
  language: z.string().nullable(),
  voices: z.array(ListedVoiceSchema),
});

/**
 * POST /v1/voices/sample, the body: which vendor, which voice, which model and which words to
 * hear. The answer is the WAV itself (`audio/wav`), with `Server-Timing: first-audio;dur=…,
 * total;dur=…` in milliseconds.
 */
export const VoiceSampleSchema = z.strictObject({
  tts: z.string(),
  voice: z.string(),
  model: z.string().nullable().nullish(),
  language: z.string().nullable().nullish(),
  text: z.string().nullable().nullish(),
});

export type VoiceSample = z.infer<typeof VoiceSampleSchema>;

/** How a judge answers: held or broken, one of its choices, or a score from 1 to 5. */
export const JudgeAnswerSchema = z.enum(["verdict", "choice", "score"]);

/** When a judge runs: every call, only a simulated one, or one its trigger says it applies to. */
export const JudgeWhenSchema = z.enum(["always", "simulations", "trigger"]);

/** What a judge reads beyond the call: the agent's prompt, the evidence it carried, its facts. */
export const JudgeReadSchema = z.enum(["prompt", "evidence", "facts"]);

/** PUT …/judges/{name}: a judge of one's own, whole, or for one of Pinecall's only `on`. */
export const JudgeRequestSchema = z.strictObject({
  question: z.string().nullish(),
  answer: JudgeAnswerSchema.nullish(),
  choices: z.array(z.string()).nullish(),
  when: JudgeWhenSchema.nullish(),
  trigger: z.string().nullish(),
  reads: z.array(JudgeReadSchema).nullish(),
  on: z.boolean().nullish(),
});

export type JudgeRequest = z.infer<typeof JudgeRequestSchema>;

/** One judge as the list shows it: whose it is (`pinecall`, `org` or the agent's slug), whether it runs, what it asks. */
export const JudgeRowSchema = z.strictObject({
  name: z.string(),
  owner: z.string(),
  on: z.boolean(),
  question: z.string(),
  answer: JudgeAnswerSchema,
  choices: z.array(z.string()),
  when: JudgeWhenSchema,
  trigger: z.string(),
  reads: z.array(JudgeReadSchema),
  summary: z.string().nullish(),
  version: z.int().nullish(),
  /** The library's: what it saves an org from, and whether Pinecall says to switch it on first. */
  why: z.string().nullish(),
  recommended: z.boolean(),
  author: z.string().nullish(),
  set_at: z.number().nullish(),
});

export type JudgeRow = z.infer<typeof JudgeRowSchema>;

/** GET /v1/agents/{slug}/judges: Pinecall's first, then the org's own, then the agent's. */
export const JudgeListSchema = z.strictObject({
  judges: z.array(JudgeRowSchema),
});

export type JudgeList = z.infer<typeof JudgeListSchema>;

/** POST /v1/agents/{slug}/judges/try: one judge, by name or written whole, asked of finished calls. */
export const JudgeTrySchema = JudgeRequestSchema.extend({
  name: z.string(),
  last: z.int().nullish(),
  calls: z.array(z.string()).nullish(),
});

export type JudgeTry = z.infer<typeof JudgeTrySchema>;

/** What a tried judge answered on each call, the evals spent and their cost; nothing is written. */
export const JudgeTriedSchema = z.strictObject({
  rows: z.array(
    z.strictObject({
      call: z.string(),
      judgment: JudgmentSchema.nullable(),
      not_judged: z.string().nullish(),
    }),
  ),
  evals: z.int(),
  cost_usd: z.number(),
});

export type JudgeTried = z.infer<typeof JudgeTriedSchema>;
