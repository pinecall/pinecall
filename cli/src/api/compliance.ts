/** The compliance endpoints: erasures and their trail, who read what, the org's policy, consent, the do-not-call list, export. */

import type { ConsentHistory, DoNotCall, DoNotCallImported, Erasure, ErasureTrail, OrgPolicy, OrgPolicyRow, Reads } from "@pinecall/agents/wire";

import { seg, type GatewayClient } from "./client.js";

export type { ConsentHistory, DoNotCall, DoNotCallImported, Erasure, ErasureTrail, OrgPolicy, OrgPolicyRow, Reads } from "@pinecall/agents/wire";

/** One ended call gone: its log, its facts, the memories it taught and its recording, in one transaction. */
export function eraseCall(gw: GatewayClient, call: string): Promise<Erasure> {
  return gw.delete<Erasure>(`/v1/calls/${seg(call)}`);
}

/** A person's "delete my data": every call they were on in this env, and every fact kept of them. */
export function eraseContact(gw: GatewayClient, contact: string): Promise<Erasure> {
  return gw.delete<Erasure>(`/v1/contacts/${seg(contact)}`);
}

export function listErasures(gw: GatewayClient): Promise<ErasureTrail> {
  return gw.get<ErasureTrail>("/v1/org/erasures");
}

export function listReads(gw: GatewayClient, subject?: string): Promise<Reads> {
  return gw.get<Reads>("/v1/org/reads", { subject });
}

export function getPolicy(gw: GatewayClient): Promise<OrgPolicyRow> {
  return gw.get<OrgPolicyRow>("/v1/org/policy");
}

/** The row is replaced whole, so one field changed is the row read and written back. */
export function putPolicy(gw: GatewayClient, policy: OrgPolicy): Promise<OrgPolicyRow> {
  return gw.put<OrgPolicyRow>("/v1/org/policy", policy);
}

export function getConsent(gw: GatewayClient, number: string): Promise<ConsentHistory> {
  return gw.get<ConsentHistory>(`/v1/org/consents/${seg(number)}`);
}

export function giveConsent(gw: GatewayClient, body: { number: string; kind: string; source: string; text: string | null; evidence: string | null }): Promise<ConsentHistory> {
  return gw.post<ConsentHistory>("/v1/org/consents", body);
}

/** The number put on the do-not-call list. */
export function optOut(gw: GatewayClient, number: string): Promise<ConsentHistory> {
  return gw.delete<ConsentHistory>(`/v1/org/consents/${seg(number)}`);
}

export function listDoNotCall(gw: GatewayClient, after?: string): Promise<DoNotCall> {
  return gw.get<DoNotCall>("/v1/org/dnc", { after });
}

export function addDoNotCall(gw: GatewayClient, numbers: string[], source: string): Promise<DoNotCallImported> {
  return gw.post<DoNotCallImported>("/v1/org/dnc", { numbers, source });
}

/** The org's env whole as JSON Lines, streamed. */
export async function exportOrg(gw: GatewayClient): Promise<ReadableStream<Uint8Array> | null> {
  return (await gw.fetch("/v1/org/export")).body;
}
