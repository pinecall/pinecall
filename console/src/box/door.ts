/** The operator's doors for orgs: every org of the box, one as it stands, and how its simulations are shaped. */

import { z } from "zod";

import { put, read, type Credentials } from "@pinecall/core/api";

const OPS = "/v1/ops";
const at = (named: string): string => `${OPS}/orgs/${encodeURIComponent(named)}`;

export const WORLDS = ["sandbox", "production"] as const;
export type World = (typeof WORLDS)[number];

// What an org nobody gave more is held to: the platform's own (runtime billing/service.py).
export const USUAL = { simulations_at_once: 10, comparison_calls: 10 } as const;

// Loose on purpose: a field the gateway adds never breaks the operator's page.
const OrgSchema = z.looseObject({ id: z.string(), slug: z.string(), name: z.string() });
export type Org = z.infer<typeof OrgSchema>;

const WorldQuotasSchema = z.looseObject({
  // null is no limit, zero refuses everything.
  limits: z.record(z.string(), z.number().nullish()),
  budget_usd: z.number().nullish(),
  lends: z.array(z.string()).nullish(),
  // null is the platform's own; a gateway from before they existed says neither.
  simulations_at_once: z.number().nullish(),
  comparison_calls: z.number().nullish(),
});
export type WorldQuotas = z.infer<typeof WorldQuotasSchema>;

const OneOrgSchema = OrgSchema.extend({
  quotas: z.record(z.string(), WorldQuotasSchema),
  holding: z.looseObject({ memory_facts: z.number(), knowledge_chunks: z.number(), numbers: z.number(), seats: z.number() }),
});
export type OneOrg = z.infer<typeof OneOrgSchema>;

export async function readOrgs(credentials: Credentials): Promise<Org[]> {
  return z.array(OrgSchema).parse(await read(credentials, `${OPS}/orgs`));
}

export async function readOrg(credentials: Credentials, named: string): Promise<OneOrg> {
  return OneOrgSchema.parse(await read(credentials, at(named)));
}

/** How the org's simulations are shaped in one world; null is the platform's own. Its monthly limits and lends are kept. */
export interface Shape {
  simulations_at_once: number | null;
  comparison_calls: number | null;
}

export async function saveShape(credentials: Credentials, named: string, world: World, shape: Shape): Promise<WorldQuotas> {
  return WorldQuotasSchema.parse(await put(credentials, `${at(named)}/simulating`, { env: world, ...shape }));
}
