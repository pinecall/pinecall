/** The operator's usage door: every organization's metered rows, a page at a time after a cursor. */

import { z } from "zod";

import { read, type Credentials } from "@pinecall/core/api";

// The org's own row (usage/door.ts) with whose it is. Loose, and every count but the first few with a
// default: a row an older gateway wrote, or a field a newer one adds, never breaks the page.
const RowSchema = z.looseObject({
  cursor: z.number(),
  /** The organization's id, never its slug: `/v1/ops/orgs` names it. */
  org: z.string(),
  agent: z.string(),
  /** Empty on a row that belongs to no call. */
  call: z.string(),
  type: z.string(),
  at: z.number(),
  minutes: z.number(),
  messages: z.number(),
  input_tokens: z.number().default(0),
  output_tokens: z.number().default(0),
  characters: z.number().default(0),
  judge_calls: z.number().default(0),
  evals: z.number().default(0),
  /** A call a simulated caller played. */
  simulated: z.boolean().default(false),
  /** What the vendors charged for it, as logged: a cost, never a price. */
  cost_usd: z.number(),
  /** The vendors that ran on the platform's own key. */
  lent: z.array(z.string()).default([]),
  caller_cost_usd: z.number().default(0),
});
export type BoxUsageRow = z.infer<typeof RowSchema>;

const PageSchema = z.looseObject({
  rows: z.array(RowSchema),
  /** Where the feed goes on; null at its end. */
  next: z.number().nullable(),
});
export type BoxUsagePage = z.infer<typeof PageSchema>;

/** The most rows the door gives in one page. */
export const A_PAGE = 500;

/** Every organization's rows after a cursor, oldest first, both environments together. */
export async function readBoxUsage(credentials: Credentials, after: number): Promise<BoxUsagePage> {
  return PageSchema.parse(await read(credentials, "/v1/ops/usage", { after, limit: A_PAGE }));
}
