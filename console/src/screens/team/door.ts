/** Team screen API: list, invite, change and remove members; org SSO. */

import { z } from "zod";

import { answered, drop, GatewayError, gatewayUrl, headersFor, post, put, read, type Credentials } from "@pinecall/core/api";
import { MemberSchema, type Member } from "@pinecall/core/members";

// Member shapes live in core, shared with the mobile app.
export { ROLES, STATUSES, readMembers, type Member } from "@pinecall/core/members";

// The invite token is returned once (only its hash is stored). Null when the person already has a
// password on this box or belongs to another org: a link would set their single password, so it
// was mailed instead (`mailed`).
const InvitedSchema = z.object({
  member: MemberSchema,
  token: z.string().nullable(),
  expires_at: z.string().nullable(),
  mailed: z.boolean(),
});
export type Invited = z.infer<typeof InvitedSchema>;

/** Invite a person; returns the row and a one-use token. */
export async function invite(
  credentials: Credentials,
  who: { email: string; name: string; role: Member["role"]; agents: string[]; production: boolean },
): Promise<Invited> {
  return InvitedSchema.parse(await post(credentials, "/v1/members", who));
}

/**
 * One-use password reset link (POST /v1/members/{id}/reset), handed on by the admin. A newer link
 * invalidates older ones.
 */
export async function resetLink(credentials: Credentials, id: string): Promise<Invited> {
  return InvitedSchema.parse(await post(credentials, `/v1/members/${encodeURIComponent(id)}/reset`, {}));
}

/** Remove a member: revokes their keys and frees the seat. Log references keep their name. */
export async function removeMember(credentials: Credentials, id: string): Promise<void> {
  await drop(credentials, `/v1/members/${encodeURIComponent(id)}`);
}

/** Update role, agents, standing or production access; omitted fields are kept. */
export async function change(
  credentials: Credentials,
  id: string,
  said: { role?: Member["role"]; agents?: string[]; status?: Member["status"]; production?: boolean },
): Promise<Member> {
  const answer = await fetch(gatewayUrl(credentials.base, `/v1/members/${encodeURIComponent(id)}`), {
    method: "PATCH",
    headers: { ...headersFor(credentials), "content-type": "application/json" },
    body: JSON.stringify(said),
  });
  return MemberSchema.parse(await answered(answer));
}

// GET /v1/org/sso: empty fields when no provider is set. The client secret is never returned.
const SsoSchema = z.object({
  configured: z.boolean(),
  issuer: z.string().nullish(),
  client_id: z.string().nullish(),
  domains: z.array(z.string()),
  role: z.string().nullish(),
  required: z.boolean(),
  redirect_uri: z.string(),
});
export type Sso = z.infer<typeof SsoSchema>;

/** PUT /v1/org/sso body: the full configuration, including the secret. */
export interface WantedSso {
  issuer: string;
  client_id: string;
  client_secret: string;
  domains: string[];
  role: Member["role"] | null;
  required: boolean;
}

/** The org's identity provider, or null when the gateway has no SSO (404). */
export async function readSso(credentials: Credentials): Promise<Sso | null> {
  try {
    return SsoSchema.parse(await read(credentials, "/v1/org/sso"));
  } catch (refused) {
    if (refused instanceof GatewayError && (refused.status === 404 || refused.status === 405)) return null;
    throw refused;
  }
}

/** Replace the org's provider; the gateway validates the issuer's discovery document first. */
export async function saveSso(credentials: Credentials, wanted: WantedSso): Promise<Sso> {
  return SsoSchema.parse(await put(credentials, "/v1/org/sso", wanted));
}

/** Remove the provider; the org falls back to passwords. */
export async function removeSso(credentials: Credentials): Promise<void> {
  await drop(credentials, "/v1/org/sso");
}
