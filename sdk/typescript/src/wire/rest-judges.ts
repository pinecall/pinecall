/** The judges' doors: a judge as a list shows it, one written or tried, and each judge's agreement with the labels people gave. */

import { z } from "zod";
import { JudgmentSchema } from "./events.js";

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
