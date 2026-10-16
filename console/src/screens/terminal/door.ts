/** Terminal screen API: look up and approve a `pinecall login` pairing code. */

import { z } from "zod";

import { post, read, type Credentials } from "@pinecall/core/api";

// The minted key goes to the terminal through its own door; this page never sees it (runtime
// api/pairing.py).
const AskedSchema = z.object({
  device: z.string().nullable(),
  expires_at: z.number(),
  answered: z.boolean(),
});

/** The pairing request: the terminal's machine name, if it sent one. */
export type Asked = z.infer<typeof AskedSchema>;

const ApprovedSchema = z.object({ device: z.string().nullable(), org: z.string(), org_name: z.string() });

function at(code: string): string {
  return `/v1/login/pairings/${encodeURIComponent(code)}`;
}

/** Look up a pairing code without consuming it, so the tab can be reloaded. */
export async function asking(credentials: Credentials, code: string): Promise<Asked> {
  return AskedSchema.parse(await read(credentials, at(code)));
}

/**
 * Approve the terminal as this person and return the name of the org it was signed in to. It gets a
 * fresh key labelled with its machine name, collected once by the CLI process; the key never passes
 * through this page.
 */
export async function approve(credentials: Credentials, code: string): Promise<string> {
  return ApprovedSchema.parse(await post(credentials, at(code), {})).org_name;
}
