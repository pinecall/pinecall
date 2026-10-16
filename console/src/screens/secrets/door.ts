/** Secrets screen API: the org's secrets in this world, listed by name, set and dropped — never read back. */

import { z } from "zod";

import { drop, put, read, type Credentials } from "@pinecall/core/api";

// runtime wire/rest/hosting.py: SecretRow. No door answers a value.
const SecretSchema = z.object({ name: z.string(), set_by: z.string(), set_at: z.number() });
const ListSchema = z.object({ secrets: z.array(SecretSchema) });

/** One of the org's secrets, by name. */
export type Secret = z.infer<typeof SecretSchema>;

const doorOf = (name: string): string => `/v1/secrets/${encodeURIComponent(name)}`;

/** The org's secrets in this world, by name. */
export async function readSecrets(credentials: Credentials): Promise<Secret[]> {
  return ListSchema.parse(await read(credentials, "/v1/secrets")).secrets;
}

/** Set a secret, replacing the value it had; answers the list. The page keeps no copy. */
export async function putSecret(credentials: Credentials, name: string, value: string): Promise<Secret[]> {
  return ListSchema.parse(await put(credentials, doorOf(name), { value })).secrets;
}

/** Forget a secret; answers the list. */
export async function dropSecret(credentials: Credentials, name: string): Promise<Secret[]> {
  return ListSchema.parse(await drop(credentials, doorOf(name))).secrets;
}
