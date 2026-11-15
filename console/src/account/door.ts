/** The account's doors: the person signed in, their name and password changed, and the keys their own sign-ins left. */

import { z } from "zod";

import { patch, put, read, type Credentials } from "@pinecall/core/api";

const MeSchema = z.looseObject({
  email: z.string(),
  name: z.string(),
  role: z.string(),
  /** False for somebody who only ever signed in through Google or their org's provider. */
  has_password: z.boolean(),
});
export type Me = z.infer<typeof MeSchema>;

export async function readMe(credentials: Credentials): Promise<Me> {
  return MeSchema.parse(await read(credentials, "/v1/me"));
}

/** Change what this org calls the person. */
export async function rename(credentials: Credentials, name: string): Promise<Me> {
  return MeSchema.parse(await patch(credentials, "/v1/me", { name }));
}

/** Change the person's one password; every other sign-in of theirs ends. */
export async function changePassword(credentials: Credentials, current: string, password: string): Promise<void> {
  await put(credentials, "/v1/me/password", { current, password });
}

const SignInSchema = z.looseObject({
  fingerprint: z.string(),
  label: z.string().nullable(),
  created_at: z.string(),
  last_used_at: z.string().nullable(),
  /** The key this page asks with. */
  current: z.boolean(),
});
export type SignIn = z.infer<typeof SignInSchema>;

export async function readSignIns(credentials: Credentials): Promise<SignIn[]> {
  return z.array(SignInSchema).parse(await read(credentials, "/v1/me/keys"));
}
