/** Sign-in: login codes, passwords, invitations, org switching, SSO and Google. */

import { z } from "zod";

import { answered, gatewayUrl, post, read, type Credentials } from "./api";

// Response of every door that mints a key (POST /v1/login and friends).
const SignedSchema = z.object({
  key: z.string(),
  key_id: z.string(),
  org: z.string(),
  label: z.string().nullish(),
  env: z.enum(["production", "sandbox"]),
  scopes: z.array(z.string()),
  subject: z.string().nullish(),
  name: z.string().nullish(),
});
export type Signed = z.infer<typeof SignedSchema>;

// `device` labels the minted key in the org's key list, so a revoked key can be identified.

/** Exchange a one-use `?login=` code for a key of this tab's own. */
export async function loginWithCode(base: string, code: string, device: string): Promise<Signed> {
  return login(base, { code, device });
}

// One-use code valid five minutes: carries a sign-in to another origin of the box's — its billing
// page — without putting the key in a URL.
const CodeSchema = z.object({ code: z.string() });

/** Mint a one-use login code for this browser's key. */
export async function aLoginCode(credentials: Credentials): Promise<string> {
  return CodeSchema.parse(await post(credentials, "/v1/login/codes", {})).code;
}

/** Sign in with email and password; `org` picks one when the person has several. */
export async function loginWithPassword(
  base: string,
  who: { org?: string; email: string; password: string },
  device: string,
): Promise<Signed> {
  return login(base, { ...who, org: who.org === undefined || who.org === "" ? null : who.org, device });
}

// GET /v1/login/orgs; `here` marks the org this key opens.
const OrgsOfSchema = z.object({
  orgs: z.array(
    z.object({
      org: z.string(),
      slug: z.string().nullish(),
      name: z.string().nullish(),
      role: z.string(),
      status: z.string(),
      here: z.boolean(),
      /** False when entering as the box operator; absent (older gateways) means member. */
      member: z.boolean().optional(),
    }),
  ),
});
export type OrgOf = z.infer<typeof OrgsOfSchema>["orgs"][number];

/** Orgs the key's person belongs to; machine keys are refused. */
export async function orgsOf(credentials: Credentials): Promise<OrgOf[]> {
  return OrgsOfSchema.parse(await read(credentials, "/v1/login/orgs")).orgs;
}

/** Mint a key for the same person in another of their orgs. */
export async function loginToOrg(credentials: Credentials, org: string): Promise<Signed> {
  return SignedSchema.parse(await post(credentials, "/v1/login/org", { org }));
}

/** Accept an invitation with a new password; the one-use token comes from the link, answer is a login. */
export async function acceptInvitation(base: string, token: string, password: string, device: string): Promise<Signed> {
  return knocked(base, `/v1/invitations/${encodeURIComponent(token)}`, { password, device });
}

// POST /v1/login/orgs: orgs an email and password open, without minting a key.
const OpensSchema = z.object({
  orgs: z.array(z.object({ org: z.string(), slug: z.string().nullish(), name: z.string().nullish(), role: z.string() })),
});
export type Opens = z.infer<typeof OpensSchema>["orgs"][number];

/**
 * Orgs these credentials open, for the sign-in org picker. Mints no key; shares the login throttle.
 * Null when the gateway lacks the door.
 */
export async function orgsForPassword(base: string, email: string, password: string): Promise<Opens[] | null> {
  const answer = await fetch(gatewayUrl(base, "/v1/login/orgs"), {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (answer.status === 404 || answer.status === 405) return null;
  return OpensSchema.parse(await answered(answer)).orgs;
}

// POST /v1/login/sso/discover: orgs with an identity provider for this email's domain.
const SsoOrgsSchema = z.object({ orgs: z.array(z.object({ org: z.string(), slug: z.string().nullish(), name: z.string().nullish() })) });
export type SsoOrg = z.infer<typeof SsoOrgsSchema>["orgs"][number];

async function discover(base: string, email: string): Promise<Response> {
  return fetch(gatewayUrl(base, "/v1/login/sso/discover"), {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ email }),
  });
}

/** Whether the gateway supports SSO (the discover door exists). Probes with an empty address. */
export async function gatewayHasSso(base: string): Promise<boolean> {
  try {
    const answer = await discover(base, "");
    return answer.status !== 404 && answer.status !== 405;
  } catch {
    return false;
  }
}

/** Orgs whose SSO covers this address; does not reveal whether the person exists. */
export async function ssoOrgsFor(base: string, email: string): Promise<SsoOrg[]> {
  return SsoOrgsSchema.parse(await answered(await discover(base, email))).orgs;
}

/** SSO start URL for an org; returns with a one-use `?login=` code. */
export function ssoUrl(base: string, org: string): string {
  return gatewayUrl(base, `/v1/login/sso?org=${encodeURIComponent(org)}`).toString();
}

/** Google sign-in URL; returns with `?login=` or `?refused=`. */
export function googleUrl(base: string): string {
  return gatewayUrl(base, "/v1/login/google").toString();
}

/** Redirect URI an operator registers with Google. */
export function googleCallback(gateway: string): string {
  return `${gateway.replace(/\/$/, "")}/v1/login/google/callback`;
}

async function login(base: string, body: unknown): Promise<Signed> {
  return knocked(base, "/v1/login", body);
}

// Unauthenticated POST for doors that mint the first key.
async function knocked(base: string, path: string, body: unknown): Promise<Signed> {
  const answer = await fetch(gatewayUrl(base, path), {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  return SignedSchema.parse(await answered(answer));
}
