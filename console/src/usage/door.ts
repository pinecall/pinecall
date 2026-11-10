/** The usage doors: each quota of the org as a limit and what is used of it, and the metered rows a page at a time. */

import { z } from "zod";

import { read, type Credentials } from "@pinecall/core/api";

const LimitSchema = z.looseObject({
  /** Null: nobody set one. */
  limit: z.number().nullable(),
  used: z.number(),
});
export type Limit = z.infer<typeof LimitSchema>;

const LimitsSchema = z.looseObject({
  minutes: LimitSchema,
  messages: LimitSchema,
  llm_tokens: LimitSchema,
  concurrent_calls: LimitSchema,
  agents: LimitSchema,
  seats: LimitSchema,
  numbers: LimitSchema,
  evals: LimitSchema,
  simulations: LimitSchema,
  memory_facts: LimitSchema,
  knowledge_chunks: LimitSchema,
  hosted_apps: LimitSchema,
  /** Dollars this month, both environments together. */
  budget_usd: LimitSchema,
  /** Where the org pays; null on a deployment that does not bill. */
  billing_url: z.string().nullable(),
});
export type Limits = z.infer<typeof LimitsSchema>;

export async function readLimits(credentials: Credentials): Promise<Limits> {
  return LimitsSchema.parse(await read(credentials, "/v1/limits"));
}

const RowSchema = z.looseObject({
  cursor: z.number(),
  agent: z.string(),
  /** Empty on a row that belongs to no call. */
  call: z.string(),
  type: z.string(),
  at: z.number(),
  minutes: z.number(),
  messages: z.number(),
  input_tokens: z.number(),
  output_tokens: z.number(),
  characters: z.number(),
  judge_calls: z.number(),
  evals: z.number(),
  /** A call a simulated caller played. */
  simulated: z.boolean(),
  cost_usd: z.number(),
  /** The vendors that ran on the platform's own key. */
  lent: z.array(z.string()).default([]),
  /** What a simulated caller's own model and voice cost, beside the call's. */
  caller_cost_usd: z.number().default(0),
});
export type UsageRow = z.infer<typeof RowSchema>;

const UsageSchema = z.looseObject({
  rows: z.array(RowSchema),
  /** Where the feed goes on; null at its end. */
  next: z.number().nullable(),
});
export type UsageRows = z.infer<typeof UsageSchema>;

/** The rows after a cursor, oldest first, 500 at most. */
export async function readUsage(credentials: Credentials, after: number): Promise<UsageRows> {
  return UsageSchema.parse(await read(credentials, "/v1/usage", { after }));
}
