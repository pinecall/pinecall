/** The org's data doors: erasures and their trail, the org's policy, consent and the do-not-call list. */

import { z } from "zod";
import { EnvSchema } from "./defs.js";

/** DELETE /v1/calls/{call}, /v1/contacts/{contact}, a row of GET /v1/org/erasures: what an erasure took. */
export const ErasureSchema = z.strictObject({
  id: z.int(),
  at: z.number(),
  what: z.enum(["call", "contact", "org"]),
  subject: z.string(),
  env: EnvSchema.nullable(),
  asked_by: z.string(),
  calls: z.int(),
  entries: z.int(),
  memories: z.int(),
  recordings: z.int(),
});

export type Erasure = z.infer<typeof ErasureSchema>;

/** GET /v1/org/erasures: the org's erasures, newest first. */
export const ErasureTrailSchema = z.strictObject({
  erasures: z.array(ErasureSchema),
});

export type ErasureTrail = z.infer<typeof ErasureTrailSchema>;

/** One read of the org's data: the call or number, what of it, who ("operator" for the box's), when. */
export const ReadRowSchema = z.strictObject({
  subject: z.string(),
  what: z.enum(["log", "recording", "traceback"]),
  env: EnvSchema.nullable(),
  reader: z.string(),
  at: z.number(),
});

/** GET /v1/org/reads: who read the org's calls, newest first. */
export const ReadsSchema = z.strictObject({ reads: z.array(ReadRowSchema) });

export type Reads = z.infer<typeof ReadsSchema>;

/** The hours of the called number's own day a call may ring: from, until (exclusive). */
export const CallingHoursSchema = z.strictObject({
  from: z.int().min(0).max(23),
  until: z.int().min(1).max(24),
});

/** PUT /v1/org/policy, the body, and the policy GET answers: retention, calling hours, calls a day per number; null is unset. */
export const OrgPolicySchema = z.strictObject({
  retention_days: z.int().positive().nullish(),
  calling_hours: CallingHoursSchema.nullish(),
  per_number_day: z.int().positive().nullish(),
  consent_everywhere: z.boolean().optional(),
  // An outbound call's opening sentence: null is the platform's, "" is none.
  disclosure: z.string().max(500).nullish(),
  recording_notice: z.boolean().optional(),
});

export type OrgPolicy = z.infer<typeof OrgPolicySchema>;

/** GET and PUT /v1/org/policy, the answer: the policy, who set it last and when. */
export const OrgPolicyRowSchema = z.strictObject({
  policy: OrgPolicySchema,
  set_by: z.string().nullable(),
  set_at: z.number().nullable(),
});

export type OrgPolicyRow = z.infer<typeof OrgPolicyRowSchema>;

/** One fact about a number: a consent or an opt-out, by whom, from what, on which call. */
export const ConsentRowSchema = z.strictObject({
  kind: z.enum(["express", "written", "opt_out"]),
  source: z.string(),
  text: z.string().nullable(),
  evidence: z.string().nullable(),
  given_by: z.string(),
  call: z.string().nullable(),
  given_at: z.number(),
});

export type ConsentRow = z.infer<typeof ConsentRowSchema>;

/** GET /v1/org/consents/{number}, and what POST and DELETE answer: what stands, and every row. */
export const ConsentHistorySchema = z.strictObject({
  number: z.string(),
  standing: z.enum(["consented", "opted_out", "unknown"]),
  rows: z.array(ConsentRowSchema),
});

export type ConsentHistory = z.infer<typeof ConsentHistorySchema>;

/** GET /v1/org/dnc: the numbers whose newest fact is an opt-out, newest first, a page. */
export const DoNotCallSchema = z.strictObject({
  numbers: z.array(z.strictObject({ number: z.string(), since: z.number(), source: z.string(), given_by: z.string() })),
  next: z.string().nullable(),
});

export type DoNotCall = z.infer<typeof DoNotCallSchema>;

/** POST /v1/org/dnc, the answer: how many joined the list, and the lines that were no number. */
export const DoNotCallImportedSchema = z.strictObject({
  added: z.int(),
  refused: z.array(z.string()),
});

export type DoNotCallImported = z.infer<typeof DoNotCallImportedSchema>;
