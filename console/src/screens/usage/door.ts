/** Usage screen API: the org's metered rows and totals. */

import { z } from "zod";

import { read, type Credentials } from "@pinecall/core/api";

// Mirrors runtime log/usage.py (UsageRow, Totals) field for field.

const RowSchema = z.object({
  cursor: z.number(),
  org: z.string(),
  agent: z.string(),
  call: z.string(),
  type: z.string(),
  at: z.number(),
  minutes: z.number(),
  messages: z.number(),
  input_tokens: z.number(),
  output_tokens: z.number(),
  characters: z.number(),
  judge_calls: z.number(),
  /** The judges that answered this call on Pinecall's key: the evals billed (a call.score row's). */
  evals: z.number(),
  /** A call.summary row of a call a simulated caller played: billed as one simulation, not minutes. */
  simulated: z.boolean(),
  cost_usd: z.number(),
});
export type UsageRow = z.infer<typeof RowSchema>;

const TotalsSchema = z.object({
  minutes: z.number(),
  messages: z.number(),
  input_tokens: z.number(),
  output_tokens: z.number(),
  characters: z.number(),
  judge_calls: z.number(),
  evals: z.number(),
  simulations: z.number(),
  cost_usd: z.number(),
  calls: z.number(),
});
export type Totals = z.infer<typeof TotalsSchema>;

const UsageSchema = z.object({ rows: z.array(RowSchema), totals: TotalsSchema.nullable(), next: z.number().nullable() });
export type UsagePage = z.infer<typeof UsageSchema>;

/** One page of metered rows after the cursor, with totals and the next cursor. */
export async function readUsage(credentials: Credentials, after = 0): Promise<UsagePage> {
  return UsageSchema.parse(await read(credentials, "/v1/usage", { after }));
}
