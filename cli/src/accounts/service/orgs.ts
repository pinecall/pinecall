/** The person's orgs at a gateway, the one a project is in, and what the gateway gives an org. */

import * as api from "../../api/accounts.js";
import { getAdvice, type Advice } from "../../api/providers.js";
import type { Context } from "../../context.js";
import { UsageError } from "../../errors.js";
import type { MachineSignIn } from "../../project/session.js";

/** The orgs the signed-in person is a member of; an org entered as an operator is not one to work in. */
export async function listOrgs(_ctx: Context, machine: MachineSignIn): Promise<api.Org[]> {
  const orgs = await api.listOrgs(api.accountsGateway(machine.url, machine.key));
  return orgs.filter((org) => org.member !== false);
}

/** The org as a person names it: its slug, or its id when the gateway carries none. */
export function slugOf(org: api.Org): string {
  return org.slug ?? org.org;
}

/** What `new` says when the person belongs to several orgs and named none, with nobody to ask. */
export function whichOrg(orgs: api.Org[]): string {
  return `which org is this project? pinecall new … --org ${orgs.map(slugOf).join(" | ")}`;
}

/**
 * The org named, or the only one; `UsageError` naming every slug when several fit and none was
 * named, or when the person is no member of the one named.
 */
export function chooseOrg(orgs: api.Org[], named: string | undefined): api.Org {
  if (named === undefined) {
    if (orgs.length === 1 && orgs[0] !== undefined) return orgs[0];
    throw new UsageError(whichOrg(orgs));
  }
  const found = orgs.find((org) => org.slug === named || org.org === named);
  if (found === undefined) throw new UsageError(`you are no member of ${named} at ${orgs.length === 0 ? "this gateway" : `this gateway: yours are ${orgs.map(slugOf).join(", ")}`}`);
  return found;
}

/** What the gateway advises this org to run, stage by stage; null from a gateway that does not say. */
export async function adviceAt(url: string, key: string): Promise<Advice | null> {
  try {
    return await getAdvice(api.accountsGateway(url, key));
  } catch {
    return null;
  }
}
