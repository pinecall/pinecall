/** The log entry and the command frame, as the socket and every door carry them. */

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

/**
 * One instruction from an app to the gateway over its WebSocket. The gateway answers with the
 * events the command produces, or with an error naming the command's id.
 */
export const CommandSchema = z.strictObject({
  type: z.string(),
  agent: z.string(),
  call: z.string().nullable(),
  id: z.string().nullish(),
  data: z.record(z.string(), z.unknown()),
});

export type Command = z.infer<typeof CommandSchema>;
