/** The providers endpoints: the vendor catalog, and the org's own provider keys, written and named but never read. */

import { seg, type GatewayClient } from "./client.js";

/** What a vendor does: the three jobs a call's pipeline has. */
export const MODALITIES = ["llm", "stt", "tts"] as const;
export type Modality = (typeof MODALITIES)[number];

/** One row of `GET /v1/providers`: a vendor this build runs. */
export interface Provider {
  name: string;
  does: Modality[];
  /** One word for what the vendor is still waiting for: `ready`, `no plugin`, `no key`, `its own`. */
  standing: string;
  /** The environment variable its key is read from on the box; null for a vendor that takes none. */
  env: string | null;
  aliases: string[];
}

/** `GET /v1/providers`: every vendor, and the one the platform runs each job on when an agent names none. */
export interface Catalog {
  providers: Provider[];
  defaults: Record<string, string>;
}

export function listProviders(gw: GatewayClient): Promise<Catalog> {
  return gw.get<Catalog>("/v1/providers");
}

/** `GET /v1/provider-keys`: the vendors the org brought a key for, by name and nothing else. */
export async function listProviderKeys(gw: GatewayClient): Promise<string[]> {
  return (await gw.get<{ vendors: string[] }>("/v1/provider-keys")).vendors;
}

/** One stage of `GET /v1/providers/advice`: the choice an agent names, and whose key it runs on. */
export interface AdvisedStage {
  stage: Modality;
  choice: string;
  /** `served here`, `lent by the host`, `your org's key` or `needs a key`. */
  runs_on: string;
  /** The open models the host's server for this stage lists. */
  served: string[];
}

/** `GET /v1/providers/advice`: what the host advises the org to run; the machine for its operator only. */
export interface Advice {
  stages: AdvisedStage[];
  lends: string[] | null;
  judge: string | null;
  caller: string | null;
  machine: Record<string, unknown> | null;
}

export function getAdvice(gw: GatewayClient): Promise<Advice> {
  return gw.get<Advice>("/v1/providers/advice");
}

export async function putProviderKey(gw: GatewayClient, vendor: string, key: string): Promise<void> {
  await gw.put(`/v1/provider-keys/${seg(vendor)}`, { key });
}

export async function deleteProviderKey(gw: GatewayClient, vendor: string): Promise<void> {
  await gw.delete(`/v1/provider-keys/${seg(vendor)}`);
}
