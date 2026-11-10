/** The team's doors: the org's people, an invitation, a change, a reset link, the seats, and the org's sign-on provider. */

import { z } from "zod";

import { drop, GatewayError, patch, post, put, read, type Credentials } from "@pinecall/core/api";
import { MemberSchema, ROLES } from "@pinecall/core/members";

/** A member as this gateway answers it: core's row, and the two flags the real rows carry. */
const PersonSchema = z.looseObject({ ...MemberSchema.shape, operator: z.boolean().optional(), verified: z.boolean().optional() });
export type Person = z.infer<typeof PersonSchema>;
export type Role = (typeof ROLES)[number];

/** What an invitation and a change both say about a person. */
export interface Access {
  role: Role;
  /** Empty is every agent. */
  agents: string[];
  production: boolean;
}

/** Every member, oldest first, the disabled among them. */
export async function readPeople(credentials: Credentials): Promise<Person[]> {
  return z.looseObject({ members: z.array(PersonSchema) }).parse(await read(credentials, "/v1/members")).members;
}

const SeatsSchema = z.looseObject({ used: z.number(), limit: z.number().nullable() });
export type Seats = z.infer<typeof SeatsSchema>;

/** The seats taken and how many the org may take; null where the gateway counts none. */
export async function readSeats(credentials: Credentials): Promise<Seats | null> {
  return z.looseObject({ seats: SeatsSchema.optional() }).parse(await read(credentials, "/v1/limits")).seats ?? null;
}

// The token comes once: only its hash is kept. Null when the link is the person's alone, mailed or not.
const LinkedSchema = z.looseObject({
  member: PersonSchema,
  token: z.string().nullable(),
  expires_at: z.string().nullable(),
  mailed: z.boolean(),
});
export type Linked = z.infer<typeof LinkedSchema>;

/** Invite a person, or mint a fresh link for one still invited; no second seat is taken. */
export async function invite(credentials: Credentials, who: Access & { email: string; name: string }): Promise<Linked> {
  return LinkedSchema.parse(await post(credentials, "/v1/members", who));
}

/** A one-use link to choose a new password; a newer one ends the older. */
export async function resetLink(credentials: Credentials, id: string): Promise<Linked> {
  return LinkedSchema.parse(await post(credentials, `/v1/members/${encodeURIComponent(id)}/reset`, {}));
}

/** Change what is named; what is left out stays. */
export async function changePerson(credentials: Credentials, id: string, said: Partial<Access> & { status?: Person["status"] }): Promise<Person> {
  return PersonSchema.parse(await patch(credentials, `/v1/members/${encodeURIComponent(id)}`, said));
}

/** Out of the org: every key revoked, the seat freed. */
export async function removePerson(credentials: Credentials, id: string): Promise<void> {
  await drop(credentials, `/v1/members/${encodeURIComponent(id)}`);
}

/** Where an invited person opens the console, on this same origin. */
export function linkOf(token: string): string {
  return `${window.location.origin}/invitations/${encodeURIComponent(token)}`;
}

// A domain signs nobody in until its TXT record was seen.
const ProofSchema = z.looseObject({ domain: z.string(), txt: z.string().nullish(), verified: z.boolean() });
export type Proof = z.infer<typeof ProofSchema>;

// The secret goes in and never comes out.
const SsoSchema = z.looseObject({
  configured: z.boolean(),
  issuer: z.string().nullish(),
  client_id: z.string().nullish(),
  domains: z.array(z.string()),
  role: z.string().nullish(),
  required: z.boolean(),
  redirect_uri: z.string(),
  proofs: z.array(ProofSchema).optional(),
});
export type Sso = z.infer<typeof SsoSchema>;

/** The provider whole, the secret with it: the gateway replaces what it held. */
export interface WantedSso {
  issuer: string;
  client_id: string;
  client_secret: string;
  domains: string[];
  role: Role | null;
  required: boolean;
}

/** The org's provider, or null on a gateway that has no single sign-on. */
export async function readSso(credentials: Credentials): Promise<Sso | null> {
  try {
    return SsoSchema.parse(await read(credentials, "/v1/org/sso"));
  } catch (refused) {
    if (refused instanceof GatewayError && (refused.status === 404 || refused.status === 405)) return null;
    throw refused;
  }
}

/** Keep the provider, once its issuer answered as one. */
export async function saveSso(credentials: Credentials, wanted: WantedSso): Promise<Sso> {
  return SsoSchema.parse(await put(credentials, "/v1/org/sso", wanted));
}

/** Forget the provider: passwords open the org again. */
export async function removeSso(credentials: Credentials): Promise<void> {
  await drop(credentials, "/v1/org/sso");
}
