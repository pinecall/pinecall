/** The door a page reads a keypad code's standing from. */

import { z } from "zod";

/**
 * GET /v1/codes/{code}: whether a call has claimed the code yet, and once one has, the call and
 * the token that reads it.
 */
export const CodeStandingSchema = z.strictObject({
  code: z.string(),
  status: z.enum(["waiting", "claimed", "expired"]),
  expires_at: z.number(),
  call: z.string().nullable(),
  log_token: z.string().nullable(),
});

