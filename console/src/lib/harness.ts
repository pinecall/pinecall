/** Where a harness row and what it lists open, whoever is in view, and whose agents it lists: the agent in view, or the org's — the ones Viewing offers. */

import { useMemo } from "react";

import { useOrg } from "./org";

/** The row itself: `/a/<agent>/<row>` with one agent in view, `/<row>` with every agent. */
export function rowAt(inView: string, row: string): string {
  return inView === "" ? `/${row}` : `/a/${encodeURIComponent(inView)}/${row}`;
}

/**
 * One thing a row lists that belongs to one agent — a persona, a case — opened on the same screen:
 * `/a/<agent>/<row>/<name>` with that agent in view, `/<row>/<owner>/<name>` with every agent, so
 * the screen never changes under the person and the URL still names whose it is.
 */
export function ownedAt(inView: string, row: string, owner: string, name: string): string {
  const named = encodeURIComponent(name);
  return inView === "" ? `/${row}/${encodeURIComponent(owner)}/${named}` : `${rowAt(inView, row)}/${named}`;
}

/** Who a person sees named on a row's screen: the agent in view, or every agent. */
export function whoseIs(inView: string): string {
  return inView === "" ? "every agent" : inView;
}

/**
 * The agents a harness row lists: the one in view, or — every agent in view — the org's, the very
 * ones Viewing offers. A persona or a run kept for a slug the org does not hold is not the org's
 * agent's, whatever it was written under. Null until the org's agents are read.
 */
export function useHarnessAgents(inView: string): readonly string[] | null {
  const { agents, agentsLoaded } = useOrg();
  const slugs = agents.map((one) => one.slug).join("\n");
  return useMemo(() => {
    if (inView !== "") return [inView];
    if (!agentsLoaded) return null;
    return slugs === "" ? [] : slugs.split("\n");
  }, [inView, agentsLoaded, slugs]);
}
