/** The evals doors a page reads: personas, their runs, the voices a caller speaks with, an agent's judges, the org's cases. */

import { z } from "zod";
import { EndReasonSchema } from "./defs.js";
import { JudgmentSchema } from "./events.js";
import { GoldenSchema } from "./rest-goldens.js";
import { SessionScoreSchema } from "./rest.js";

/**
 * One synthetic caller of ONE agent, kept by the gateway: what they want, how they talk, and what
 * they may state about themselves. A model plays them turn by turn — there is no script — for
 * `pinecall simulate` and the console's Simulations. Another agent of the org has callers of its
 * own, even under the same name.
 */
/** What a line can carry behind the caller once `interferer_db` sets a level. */
export const AMBIENCES = ["television", "cafe", "office", "street"] as const;

export type Ambience = (typeof AMBIENCES)[number];

/** How a simulated caller acts on a spoken line, beside what it says. */
export const CallerBehaviorSchema = z.strictObject({
  /** The share of the agent's answers it talks over, some way into them: 0 to 1. */
  interrupts: z.number(),
  /** Seconds of silence before each line. */
  pause_s: z.number(),
  interferer_db: z.number().nullable(),
  packet_loss: z.number(),
  /** The share of the answers it murmurs an "mm-hmm" into without taking its turn: 0 to 1. */
  backchannels: z.number(),
  /** How fast it speaks: 1 as the vendor reads it, 0.5 half as fast, 2 twice. */
  speed: z.number(),
  ambience: z.enum(AMBIENCES),
});

export type CallerBehavior = z.infer<typeof CallerBehaviorSchema>;

export const PersonaSchema = z.strictObject({
  /** The agent the caller was written for: every row says whose, so the org's roster reads the same. */
  agent: z.string(),
  name: z.string(),
  /** "pinecall" for the library's, else the agent's slug. */
  owner: z.string(),
  /** Whether the agent's runs play it; the agent's own always do. */
  on: z.boolean(),
  about: z.string(),
  goal: z.string(),
  style: z.string(),
  facts: z.record(z.string(), z.string()),
  state: z.record(z.string(), z.unknown()),
  llm: z.string().nullable(),
  tts: z.string().nullable(),
  voice: z.string().nullable(),
  /** What the caller expects of the agent, one demand a line: the expected-outcome judge reads them. */
  expects: z.array(z.string()),
  tags: z.array(z.string()),
  behavior: CallerBehaviorSchema,
  /** The library's: what it is for, and the version of its page. */
  summary: z.string().nullish(),
  version: z.int().nullish(),
  author: z.string().nullish(),
  set_at: z.number().nullish(),
});

export type Persona = z.infer<typeof PersonaSchema>;

/** GET /v1/agents/{slug}/personas: every caller written for the agent, by name; GET /v1/personas: every agent's, by agent. The same in both worlds. */
export const PersonaListSchema = z.strictObject({
  personas: z.array(PersonaSchema),
});

/**
 * PUT /v1/agents/{slug}/personas/{name}, the body: the caller, written whole. A name that exists
 * is replaced; `was` renames the agent's caller it names.
 */
export const PersonaPutSchema = z.strictObject({
  about: z.string().nullish(),
  goal: z.string(),
  style: z.string(),
  facts: z.record(z.string(), z.string()).nullish(),
  state: z.record(z.string(), z.unknown()).nullish(),
  llm: z.string().nullable().nullish(),
  tts: z.string().nullable().nullish(),
  voice: z.string().nullable().nullish(),
  expects: z.array(z.string()).nullish(),
  tags: z.array(z.string()).nullish(),
  behavior: CallerBehaviorSchema.partial().nullish(),
  was: z.string().nullish(),
  /** One of Pinecall's: whether the agent's runs play it, and nothing else. */
  on: z.boolean().nullish(),
});

export type PersonaPut = z.infer<typeof PersonaPutSchema>;

/** A caller the judge model wrote for the agent, saved nowhere until it is PUT. */
export const ProposedPersonaSchema = z.strictObject({
  name: z.string(),
  about: z.string(),
  goal: z.string(),
  style: z.string(),
  facts: z.record(z.string(), z.string()),
  expects: z.array(z.string()),
  tags: z.array(z.string()),
  behavior: CallerBehaviorSchema,
});

export type ProposedPersona = z.infer<typeof ProposedPersonaSchema>;

/** POST /v1/agents/{slug}/personas/generate: the callers written, their evals, their cost. */
export const GeneratedPersonasSchema = z.strictObject({
  personas: z.array(ProposedPersonaSchema),
  evals: z.int(),
  cost_usd: z.number(),
});

export type GeneratedPersonas = z.infer<typeof GeneratedPersonasSchema>;

/** A diagnosis of a case group: the cause the calls share, and the change it proposes. */
export const ProposalSchema = z.strictObject({
  cause: z.string(),
  kind: z.enum(["setting", "code", "knowledge", "none"]),
  where: z.string(),
  change: z.unknown(),
  confidence: z.number(),
});

export type Proposal = z.infer<typeof ProposalSchema>;

/** Cases one judge broke on for one agent: the cause, how many, and what to change. */
export const CaseGroupSchema = z.strictObject({
  id: z.string(),
  agent: z.string(),
  judge: z.string(),
  cause: z.string(),
  status: z.enum(["pending", "approved", "dismissed"]),
  since: z.number(),
  cases: z.int(),
  simulations: z.int(),
  proposal: ProposalSchema.nullish(),
  proposed_at: z.number().nullish(),
});

export type CaseGroup = z.infer<typeof CaseGroupSchema>;

/** GET /v1/evals/groups: the org's groups, the pending first. */
export const CaseGroupListSchema = z.strictObject({
  groups: z.array(CaseGroupSchema),
});

/**
 * One simulation this caller has run: the call it was, and what the call came to. Read off the
 * call index, never off a log — the same row the sessions list is drawn from.
 */
export const PersonaRunSchema = z.strictObject({
  call: z.string(),
  agent: z.string(),
  /** Who played it: every simulated call names its persona. */
  persona: z.string().nullable(),
  started_at: z.number(),
  ended_at: z.number().nullable(),
  turns: z.int(),
  end_reason: EndReasonSchema.nullable(),
  outcome: z.string().nullable(),
  cost_usd: z.number().nullable(),
  score: SessionScoreSchema.nullable(),
  /** Who played the caller as it ran: `vendor/model` of its lines and of its voice, and the voice; null before the runtime kept it. */
  played_by: z.strictObject({ llm: z.string().nullable(), tts: z.string().nullable(), voice: z.string().nullable() }).nullable(),
  /** What that caller's lines and voice cost, in US dollars. */
  caller_cost_usd: z.number(),
});

export type PersonaRun = z.infer<typeof PersonaRunSchema>;

/**
 * Simulated calls, newest first, a page at a time: one caller's to the agent (GET
 * /v1/agents/{slug}/personas/{name}/runs), or every one of the world (GET /v1/simulations) — in the
 * key's own world and corner, paged exactly as the sessions list is.
 */
export const PersonaRunListSchema = z.strictObject({
  runs: z.array(PersonaRunSchema),
  total: z.int(),
  next: z.string().nullable(),
});

export type PersonaRunList = z.infer<typeof PersonaRunListSchema>;

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

export type ListedVoice = z.infer<typeof ListedVoiceSchema>;

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

export type JudgeAnswer = z.infer<typeof JudgeAnswerSchema>;

/** When a judge runs: every call, only a call a simulated caller played, or a call its trigger says it applies to. */
export const JudgeOnSchema = z.enum(["always", "simulations", "trigger"]);

export type JudgeOn = z.infer<typeof JudgeOnSchema>;

/** What a judge reads beyond the call and its tool calls, each one more block of its question. */
export const JudgeReadSchema = z.enum(["prompt", "evidence", "facts"]);

export type JudgeRead = z.infer<typeof JudgeReadSchema>;

/**
 * One judge as a list shows it: Pinecall's library's (`owner` "pinecall", switched by `on`), the
 * org's own (`owner` "org") or an agent's own (`owner` its slug), what it asks, how it answers,
 * when it runs and what it reads. One list serves both worlds.
 */
export const JudgeRowSchema = z.strictObject({
  name: z.string(),
  owner: z.string(),
  on: z.boolean(),
  question: z.string(),
  answer: JudgeAnswerSchema,
  choices: z.array(z.string()),
  when: JudgeOnSchema,
  trigger: z.string(),
  reads: z.array(JudgeReadSchema),
  /** The library's: one line on what it holds a call to, and the version of its question. */
  summary: z.string().nullish(),
  version: z.int().nullish(),
  /** The library's: what it saves an org from, in a line, and whether Pinecall says to switch it on first. */
  why: z.string().nullish(),
  recommended: z.boolean(),
  /** One of the org's own: who wrote it last, and when. */
  author: z.string().nullish(),
  set_at: z.number().nullish(),
});

export type JudgeRow = z.infer<typeof JudgeRowSchema>;

/** GET /v1/org/judges and /v1/agents/{slug}/judges, and what PUT and DELETE answer: the library first, then the org's own, then the agent's. */
export const JudgeListSchema = z.strictObject({
  judges: z.array(JudgeRowSchema),
});

/** PUT …/judges/{name}: one of the org's own written whole, or for one of Pinecall's only `on`. */
export const JudgeRequestSchema = z.strictObject({
  question: z.string().nullish(),
  answer: JudgeAnswerSchema.nullish(),
  choices: z.array(z.string()).nullish(),
  when: JudgeOnSchema.nullish(),
  trigger: z.string().nullish(),
  reads: z.array(JudgeReadSchema).nullish(),
  on: z.boolean().nullish(),
});

export type JudgeRequest = z.infer<typeof JudgeRequestSchema>;

/** POST /v1/agents/{slug}/judges/try: one judge, by name alone or written whole, asked of the agent's last calls or of the calls named. Nothing is kept. */
export const JudgeTrySchema = JudgeRequestSchema.extend({
  name: z.string(),
  last: z.int().min(1).max(50).nullish(),
  calls: z.array(z.string()).max(50).nullish(),
});

export type JudgeTry = z.infer<typeof JudgeTrySchema>;

/** One judge against the labels people gave: how many, how many compared, how many agreed, and whether it is trusted. */
export const JudgeAgreementSchema = z.strictObject({
  judge: z.string(),
  labelled: z.int(),
  compared: z.int(),
  agreed: z.int(),
  rate: z.number().nullable(),
  /** null until enough labels were compared to say; false is a judge under its line. */
  trusted: z.boolean().nullable(),
});

export type JudgeAgreement = z.infer<typeof JudgeAgreementSchema>;

/** GET /v1/evals/calibration: each judge's agreement with the labels, and the line it is held to. */
export const CalibrationSchema = z.strictObject({
  judges: z.array(JudgeAgreementSchema),
  labels_to_judge: z.int(),
  agrees_at_least: z.number(),
});

export type Calibration = z.infer<typeof CalibrationSchema>;

/** What the judge answered of one call, or why it did not. */
export const JudgeTriedRowSchema = z.strictObject({
  call: z.string(),
  judgment: JudgmentSchema.nullable(),
  not_judged: z.string().nullish(),
});

export type JudgeTriedRow = z.infer<typeof JudgeTriedRowSchema>;

/** The try's answer: every call's row, the evals it spent and what they cost. */
export const JudgeTriedSchema = z.strictObject({
  rows: z.array(JudgeTriedRowSchema),
  evals: z.int(),
  cost_usd: z.number(),
});

export type JudgeTried = z.infer<typeof JudgeTriedSchema>;

/** A case waits for a person (`pending`) until approved into the nightly or dismissed. */
export const CaseStatusSchema = z.enum(["pending", "approved", "dismissed"]);

export type CaseStatus = z.infer<typeof CaseStatusSchema>;

/**
 * One case of the org's dataset: a real call kept as a golden — at hang-up when a judge broke on
 * it, or by a person — whose agent, from which world, on which settings version, and decided how.
 */
export const EvalCaseSchema = z.strictObject({
  id: z.string(),
  agent: z.string(),
  name: z.string(),
  golden: GoldenSchema,
  source_call: z.string(),
  source_env: z.enum(["production", "sandbox"]),
  held_out: z.boolean(),
  author: z.string(),
  created_at: z.number(),
  status: CaseStatusSchema,
  broke: z.array(z.strictObject({ judge: z.string(), reason: z.string() })),
  source_version: z.number().nullable(),
  kept_in_repo: z.boolean(),
  decided_by: z.string().nullable(),
  /** The group of cases its judge broke on; null for one a person kept. */
  group: z.string().nullish(),
  /** A real call, a simulation a persona played, or a person who wrote it by hand (no call: `source_call` is ""). */
  source: z.enum(["call", "simulation", "person"]).nullish(),
  persona: z.string().nullish(),
});

export type EvalCase = z.infer<typeof EvalCaseSchema>;

/** GET /v1/evals/cases: the org's cases, the pending first, and how many wait of how many may. */
export const EvalCaseListSchema = z.strictObject({
  cases: z.array(EvalCaseSchema),
  pending: z.number(),
  pending_at_most: z.number(),
});

/** PUT /v1/agents/{slug}/cases/{name}, the body: a golden a person wrote, held out of the nightly or not. */
export const WriteCaseSchema = z.strictObject({
  golden: GoldenSchema,
  held_out: z.boolean().optional(),
});

export type WriteCase = z.infer<typeof WriteCaseSchema>;

/** PATCH /v1/evals/cases/{id}, the body: what a person decided; each field sent is written. */
export const CaseDecisionSchema = z.strictObject({
  status: CaseStatusSchema.optional(),
  held_out: z.boolean().optional(),
  kept_in_repo: z.boolean().optional(),
  judge_was_wrong: z.string().optional(),
  note: z.string().optional(),
});

export type CaseDecision = z.infer<typeof CaseDecisionSchema>;

/** The numbers a monitor can watch (runtime domain/monitor.py): latencies in seconds at the median, rates as shares of 1, spend in dollars, calls. */
export const MonitorMetricSchema = z.enum(["e2e_median_s", "llm_median_s", "held_rate", "escalated_rate", "tool_failure_rate", "spend_usd", "calls"]);

export type MonitorMetric = z.infer<typeof MonitorMetricSchema>;

/**
 * One monitor of the world (runtime wire/rest/monitors.py: MonitorRow): what it watches over
 * which window, the line it must not cross, and the last day it did with the value that crossed.
 */
export const MonitorSchema = z.strictObject({
  id: z.string(),
  name: z.string(),
  metric: z.string(),
  above: z.boolean(),
  threshold: z.number(),
  window_days: z.number(),
  agent: z.string().nullable(),
  created_by: z.string(),
  fired_on: z.string().nullable(),
  fired_value: z.number().nullable(),
});

export type Monitor = z.infer<typeof MonitorSchema>;

/** GET /v1/monitors: every monitor of the world, oldest first. */
export const MonitorListSchema = z.strictObject({ monitors: z.array(MonitorSchema) });

/** POST /v1/monitors, the body: the rule, and whose agent — every agent's calls when null. */
export const MonitorPutSchema = z.strictObject({
  name: z.string(),
  metric: MonitorMetricSchema,
  above: z.boolean(),
  threshold: z.number(),
  window_days: z.union([z.literal(1), z.literal(7), z.literal(30)]),
  agent: z.string().nullable(),
});

export type MonitorPut = z.infer<typeof MonitorPutSchema>;
