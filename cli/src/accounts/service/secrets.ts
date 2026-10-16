/** The org's secrets: what its hosted apps are started with, per env, set and dropped, never read back. */

import { z } from "zod";

import * as api from "../../api/accounts.js";
import type { Context } from "../../context.js";
import { UsageError } from "../../errors.js";

const A_NAME = /^[A-Z][A-Z0-9_]*$/;

/** What `secrets set` takes: the name, and the value read off stdin, never a flag. */
export const SetSecretInput = z.object({
  name: z.string().min(1),
  value: z.string(),
});
export type SetSecretInput = z.infer<typeof SetSecretInput>;

export async function listSecrets(ctx: Context): Promise<api.SecretList> {
  return api.listSecrets(ctx.gateway());
}

/** Keep one; the same name again replaces it. The apps of the org in this env start again with it. */
export async function setSecret(ctx: Context, input: SetSecretInput): Promise<{ name: string }> {
  checkSecretName(input.name);
  if (input.value === "") throw new UsageError(`no value for ${input.name}: type it, or pipe it in`);
  await api.setSecret(ctx.gateway(), input.name, input.value);
  return { name: input.name };
}

export async function removeSecret(ctx: Context, name: string): Promise<{ name: string }> {
  checkSecretName(name);
  await api.deleteSecret(ctx.gateway(), name);
  return { name };
}

/** A secret's name is an environment variable's, and never one Pinecall sets itself. */
export function checkSecretName(name: string): void {
  if (!A_NAME.test(name)) throw new UsageError(`${name} is no name for a secret: capitals, digits and underscores, like CRM_TOKEN`);
  if (name.startsWith("PINECALL_")) throw new UsageError(`${name} is Pinecall's to set: a secret never starts with PINECALL_`);
}
