/** Tying the project's folder to one of the person's orgs: their orgs, the key minted in the one chosen, the `.env` it is written to. */

import { join } from "node:path";

import { z } from "zod";

import * as api from "../../api/accounts.js";
import type { Context } from "../../context.js";
import { UsageError } from "../../errors.js";
import { DOTENV, writeDotenv } from "../../kit/dotenv.js";
import { ignoredByGit } from "../../kit/git.js";
import { CLOUD_URL, KEY_VARIABLE, URL_VARIABLE } from "../../project/credentials.js";
import type { MachineSignIn } from "./home.js";

/** What `link` takes: which org when the person has several, and which gateway when not the last signed in to. */
export const LinkInput = z.object({
  org: z.string().min(1).optional(),
  gateway: z.string().url().optional(),
});
export type LinkInput = z.infer<typeof LinkInput>;

/** What `link` did: the org, the variables written, the file, and whether git leaves it alone. */
export interface Linked {
  org: string;
  written: string[];
  file: string;
  gitIgnored: boolean;
}

/** The orgs the signed-in person is a member of; an org entered as an operator cannot be linked. */
export async function listOrgs(_ctx: Context, machine: MachineSignIn): Promise<api.Org[]> {
  const orgs = await api.listOrgs(api.accountsGateway(machine.url, machine.key));
  return orgs.filter((org) => org.member !== false);
}

/** The org as a person names it: its slug, or its id when the gateway carries none. */
export function slugOf(org: api.Org): string {
  return org.slug ?? org.org;
}

/**
 * The org named, or the only one; `UsageError` naming every slug when several fit and none was
 * named, or when the person is no member of the one named.
 */
export function chooseOrg(orgs: api.Org[], named: string | undefined): api.Org {
  const slugs = orgs.map(slugOf).join(" | ");
  if (named === undefined) {
    if (orgs.length === 1 && orgs[0] !== undefined) return orgs[0];
    throw new UsageError(`which org is this project? --org ${slugs}`);
  }
  const found = orgs.find((org) => org.slug === named || org.org === named);
  if (found === undefined) throw new UsageError(`you are no member of ${named}: --org ${slugs}`);
  return found;
}

/**
 * The person's key in the chosen org — the machine's own when it is already that org's, else one
 * minted there — written into the project's `.env` with the gateway beside it when it is not Pinecall
 * Cloud; every other line of the file is left as it was.
 */
export async function linkProject(ctx: Context, machine: MachineSignIn, org: api.Org): Promise<Linked> {
  const gw = api.accountsGateway(machine.url, machine.key);
  const key = org.here ? machine.key : await api.createOrgKey(gw, org.org);
  const file = join(ctx.cwd, DOTENV);
  const values: Record<string, string> = { [KEY_VARIABLE]: key };
  if (machine.url !== CLOUD_URL) values[URL_VARIABLE] = machine.url;
  writeDotenv(file, values);
  return { org: slugOf(org), written: Object.keys(values), file, gitIgnored: ignoredByGit(file) };
}
