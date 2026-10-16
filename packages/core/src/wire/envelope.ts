/** The log entry, as every door and stream carries it. */

import { z } from "zod";

/**
 * One line of a call's log, or of an agent's log when call is null. seq is written before control
 * returns, so two readers never disagree about order.
 */
export const EntrySchema = z.strictObject({
  seq: z.int(),
  ts: z.number(),
  call: z.string().nullable(),
  agent: z.string(),
  type: z.string(),
  ephemeral: z.boolean(),
  data: z.record(z.string(), z.unknown()),
});

export type Entry = z.infer<typeof EntrySchema>;
