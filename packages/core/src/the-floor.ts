/** Read the gateway's unauthenticated discovery document (/.well-known/pinecall). */

import { z } from "zod";

import { answered, gatewayUrl } from "./api";

// Loose and mostly optional: newer gateways add fields, older ones lack some.
const DiscoveredSchema = z.looseObject({
  version: z.string(),
  cloud: z.boolean().optional(),
  signup: z.boolean(),
  min_password: z.number(),
  /** The box can send mail (password reset is available). */
  mail: z.boolean().optional(),
  /** Google sign-in is configured. */
  google: z.boolean().optional(),
});

/** The gateway's discovery document. */
export type Discovered = z.infer<typeof DiscoveredSchema>;

/**
 * Fetch the discovery document. On failure assume no sign-up and no password minimum, so the page
 * never rejects a password the gateway would accept.
 */
export async function discovered(base: string): Promise<Discovered> {
  try {
    const answer = await fetch(gatewayUrl(base, "/.well-known/pinecall"));
    return DiscoveredSchema.parse(await answered(answer));
  } catch {
    return { version: "", cloud: false, signup: false, min_password: 0 };
  }
}
