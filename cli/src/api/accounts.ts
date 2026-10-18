/** The accounts endpoints: who a key is, the sign-in pairing, the person's orgs, the console's login codes, the org's secrets and its people. */

import type { SecretList } from "@pinecall/agents/wire";

import { GatewayClient, seg } from "./client.js";

export type { SecretList };

/** One row of `GET /v1/secrets`: a name, who set it and when; never a value. */
export type SecretRow = SecretList["secrets"][number];

/** `GET /v1/whoami`: the gateway's description of a key, never the key or its hash. */
export interface Whoami {
  org: string;
  /** The org's human-readable slug, e.g. `clinica`; absent on older gateways. */
  slug?: string | null;
  key_id: string;
  label: string | null;
  /** The env this request acted in. */
  env: string;
  /** The person the key was minted for; absent for a server token. */
  name?: string | null;
  /** Whether this key may act in production (the person's switch, any admin, or a production token). */
  production: boolean;
}

/** One org of `GET /v1/login/orgs`. */
export interface Org {
  org: string;
  slug?: string | null;
  /** Whether the key asking is this org's. */
  here: boolean;
  /** False for orgs an operator can enter without membership; a project is never made to run in those. */
  member?: boolean;
}

/**
 * The gateway for a sign-in: accounts exist only in production, and a pairing is opened with no
 * key at all. A key in another of the person's orgs is minted from the machine's own through the same client.
 */
export function accountsGateway(url: string, key = ""): GatewayClient {
  return new GatewayClient(url, key, "production");
}

export function getWhoami(gw: GatewayClient): Promise<Whoami> {
  return gw.get<Whoami>("/v1/whoami");
}

/** `POST /v1/login/pairings`: a one-use code the sign-in page takes, labelled with this machine. */
export async function createPairing(gw: GatewayClient, device: string): Promise<string> {
  return (await gw.post<{ code: string }>("/v1/login/pairings", { device })).code;
}

/**
 * `GET /v1/login/pairings/{code}/key`: the key once a person approved the code; the gateway holds
 * the ask up to `waitS` seconds and answers 202 with no key when nobody came in time.
 */
export async function getPairingKey(gw: GatewayClient, code: string, waitS: number, signal?: AbortSignal): Promise<string | undefined> {
  const answered = await gw.get<{ key?: string } | null>(`/v1/login/pairings/${seg(code)}/key`, { wait_s: waitS }, signal);
  return answered?.key;
}

/** `GET /v1/login/orgs`: every org the signed-in person may enter. */
export async function listOrgs(gw: GatewayClient): Promise<Org[]> {
  return (await gw.get<{ orgs: Org[] }>("/v1/login/orgs")).orgs;
}

/** `POST /v1/login/org`: the person's key minted in one of their orgs. */
export async function createOrgKey(gw: GatewayClient, org: string): Promise<string> {
  return (await gw.post<{ key: string }>("/v1/login/org", { org })).key;
}

/** `POST /v1/login/codes`: a one-use code that signs a browser into the console, for five minutes. */
export async function createLoginCode(gw: GatewayClient): Promise<string> {
  return (await gw.post<{ code: string }>("/v1/login/codes", {})).code;
}

export function listSecrets(gw: GatewayClient): Promise<SecretList> {
  return gw.get<SecretList>("/v1/secrets");
}

export function setSecret(gw: GatewayClient, name: string, value: string): Promise<SecretList> {
  return gw.put<SecretList>(`/v1/secrets/${seg(name)}`, { value });
}

export function deleteSecret(gw: GatewayClient, name: string): Promise<SecretList> {
  return gw.delete<SecretList>(`/v1/secrets/${seg(name)}`);
}

/** One row of `GET /v1/members`: a person of the org, never a password nor a link. */
export interface MemberRow {
  id: string;
  email: string;
  name: string;
  role: string;
  status: string;
  operator: boolean;
  production: boolean;
}

/** `POST /v1/members/{id}/reset`: the member, and the one-use link when the gateway hands it over. */
export interface Invited {
  member: MemberRow;
  token: string | null;
  link?: string | null;
  mailed: boolean;
}

export function listMembers(gw: GatewayClient): Promise<{ members: MemberRow[] }> {
  return gw.get<{ members: MemberRow[] }>("/v1/members");
}

/** `PUT /v1/members/{id}/password`: an admin sets a member's password; an invited member becomes active. */
export function setMemberPassword(gw: GatewayClient, member: string, password: string): Promise<MemberRow> {
  return gw.put<MemberRow>(`/v1/members/${seg(member)}/password`, { password });
}

export function resetMember(gw: GatewayClient, member: string): Promise<Invited> {
  return gw.post<Invited>(`/v1/members/${seg(member)}/reset`, {});
}
