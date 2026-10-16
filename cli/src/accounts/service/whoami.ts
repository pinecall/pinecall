/** Who the project's key is at its gateway, and the console's one-use login code minted on it. */

import * as api from "../../api/accounts.js";
import type { Context } from "../../context.js";

/** Ask the gateway who the project's key is, in the env chosen. */
export async function getWhoami(ctx: Context): Promise<api.Whoami> {
  return api.getWhoami(ctx.gateway());
}

/** A one-use code that signs a browser into the console, for five minutes, in the env chosen. */
export async function createLoginCode(ctx: Context): Promise<string> {
  return api.createLoginCode(ctx.gateway());
}

/** The org as a person names it: its slug, or its id on a gateway too old to carry one. */
export function orgOf(who: Pick<api.Whoami, "org" | "slug">): string {
  return who.slug ?? who.org;
}

/** The person a key was minted for, as `login` greets them; a label, or a stand-in, for a key without one. */
export function personOf(who: api.Whoami): string {
  return who.name ?? who.label ?? "this key's person";
}
