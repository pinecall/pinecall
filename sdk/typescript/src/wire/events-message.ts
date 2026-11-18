/** What a written channel says of a message: where a reply stands, one that waits for an agent, one taken. */

import { z } from "zod";
import { ChannelSchema, EnvSchema } from "./defs.js";

/** Where a message the agent wrote stands with its contact: sent, delivered, read, or failed. */
export const MessageStatusSchema = z.strictObject({
  message_id: z.string(),
  status: z.string(),
  to: z.string(),
  error: z.string().nullable(),
});

/** One waiting message, off the queue. */
export const MessageTakenSchema = z.strictObject({
  message_id: z.string(),
  call: z.string().nullable(),
});

/** One message, kept until somebody can answer it. */
export const MessageWaitingSchema = z.strictObject({
  channel: ChannelSchema,
  env: EnvSchema,
  number: z.string(),
  phone_number_id: z.string(),
  from: z.string(),
  name: z.string().nullable(),
  message_id: z.string(),
  text: z.string(),
  received_at: z.number(),
});
