/** Tokens screen API: list, create and revoke personal and server tokens. */

import { z } from "zod";

import { post, read, type Credentials } from "@pinecall/core/api";

// Listings carry no key (only its sha256 is stored). Personal keys have no world; server tokens
// are bound to one world and belong to the org, not their creator.
const ListedSchema = z.object({
  fingerprint: z.string(),
  label: z.string().nullable(),
  kind: z.enum(["person", "server"]),
  env: z.enum(["production", "sandbox"]).nullable(),
  name: z.string().nullable(),
  created_by: z.string().nullable(),
  created_at: z.string(),
  last_used_at: z.string().nullable(),
  revoked_at: z.string().nullable(),
  scopes: z.array(z.string()),
});

// The only response carrying a key in the clear: show it once and keep it in no state.
const IssuedSchema = z.object({
  key: z.string(),
  key_id: z.string(),
  label: z.string().nullable(),
  env: z.string(),
  scopes: z.array(z.string()),
});

/** A listed token. */
export type Listed = z.infer<typeof ListedSchema>;

/** A newly created token, with its key in the clear. */
export type Issued = z.infer<typeof IssuedSchema>;

/** Tokens visible to this key, oldest first, including revoked ones. */
export async function readTokens(credentials: Credentials): Promise<Listed[]> {
  return z.array(ListedSchema).parse(await read(credentials, "/v1/keys"));
}

/** Create a server token for one world. */
export async function makeToken(credentials: Credentials, wanted: { label: string; env: "production" | "sandbox" }): Promise<Issued> {
  return IssuedSchema.parse(await post(credentials, "/v1/keys", wanted));
}

/** Revoke a token from the next request; its row and calls are kept. */
export async function revokeToken(credentials: Credentials, fingerprint: string): Promise<void> {
  await post(credentials, `/v1/keys/${encodeURIComponent(fingerprint)}/revoke`, {});
}
