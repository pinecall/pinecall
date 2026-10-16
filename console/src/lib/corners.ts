/** Per-person agent copies (sandbox corners): filtering and ownership. */

import { type HeldAgent } from "@pinecall/core/wire/rest-org";

import type { Whose } from "./whoami";

export type Corners = "everything" | "mine" | "the team's";

export const CORNERS: readonly Corners[] = ["everything", "mine", "the team's"];

/** Whether this row is another member's copy. Org-owned rows (no holder) never are. */
export function somebodyElses(held: HeldAgent, me: string | null | undefined): boolean {
  const whose = held.holder?.holder;
  return whose !== undefined && whose !== null && whose !== me;
}

/** Filter rows by corner. */
export function through(agents: HeldAgent[], corners: Corners, me: string | null | undefined): HeldAgent[] {
  if (corners === "everything") return agents;
  const theirs = corners === "the team's";
  return agents.filter((held) => somebodyElses(held, me) === theirs);
}

/**
 * One row per slug, preferring the reader's own copy.
 *
 * Agent routes are addressed by slug only and the gateway resolves the corner from the key, so
 * offering a colleague's copy in a selector would still open the reader's own.
 */
export function bySlug(agents: HeldAgent[], me: string | null | undefined): HeldAgent[] {
  const kept = new Map<string, HeldAgent>();
  for (const held of agents) {
    const standing = kept.get(held.slug);
    if (standing === undefined || (somebodyElses(standing, me) && !somebodyElses(held, me))) {
      kept.set(held.slug, held);
    }
  }
  return [...kept.values()];
}

/** Display name of a row's holder, or "the org's". */
export function whoseCorner(held: HeldAgent): string {
  const whose = held.holder;
  if (whose === undefined || whose === null) return "the org's";
  return whose.name ?? whose.holder ?? "the org's";
}

/** The current member's subject, or null for a key without one. */
export function meIn(whose: Whose | null): string | null {
  return whose?.subject ?? null;
}
