/** Sign-up: an org made from a mailed code, where the gateway opens them (`/.well-known/pinecall` says). */

import { z } from "zod";

import { answered, gatewayUrl } from "./api";
import { SignedSchema, type Signed, type TurnstileToken } from "./login";

/** What a stranger fills in: the company, who they are, the password they will sign in with. */
export interface SignUpAsked {
  /** The org's name; the gateway makes its slug of it. */
  name: string;
  person: string;
  email: string;
  password: string;
}

// POST /v1/signup: where the code went and when it dies; never the code.
const CodeMailedSchema = z.object({ email: z.string(), code_expires_at: z.number() });
export type CodeMailed = z.infer<typeof CodeMailedSchema>;

/** Keep the sign-up at the gateway, which mails six digits to the address. */
export async function signUp(base: string, asked: SignUpAsked, device: string, turnstile: TurnstileToken = null): Promise<CodeMailed> {
  return CodeMailedSchema.parse(await answered(await knock(base, "/v1/signup", { ...asked, device, turnstile })));
}

// POST /v1/signup/verify: the key shape, plus the org's slug (and a login code this page never needs).
const OrgMadeSchema = SignedSchema.extend({ slug: z.string() });
export type OrgMade = z.infer<typeof OrgMadeSchema>;

/** The mailed code back: the org made, and a key of this tab's own in it. */
export async function verifySignUp(base: string, email: string, code: string, device: string): Promise<OrgMade & Signed> {
  return OrgMadeSchema.parse(await answered(await knock(base, "/v1/signup/verify", { email, code, device })));
}

/** A new code for a sign-up still waiting; the gateway answers alike whoever asks. */
export async function resendSignUpCode(base: string, email: string, turnstile: TurnstileToken = null): Promise<void> {
  await answered(await knock(base, "/v1/signup/resend", { email, turnstile }));
}

// Unauthenticated POST: these doors take no key, since they make the first one.
async function knock(base: string, path: string, body: unknown): Promise<Response> {
  return fetch(gatewayUrl(base, path), {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
}
