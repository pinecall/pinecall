/** Send a supervisor verb to a live call. */

import { type Verb, VerbSchema } from "./wire/verbs.js";

import { post, type Credentials } from "./api";

// Parsed client-side so a malformed verb throws here, not as a 422. The door answers 202 and the
// effect shows up in the log (gateway-api.md §4).
/** Send one verb on one call. Rejects with the gateway's refusal. */
export async function sendVerb(credentials: Credentials, call: string, verb: Verb): Promise<void> {
  await post(credentials, `/v1/calls/${call}/verbs`, VerbSchema.parse(verb));
}
