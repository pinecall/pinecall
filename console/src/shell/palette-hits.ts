/** What ⌘K can land on — a screen, an agent, a call — each a row saying how it is drawn and what words find it. */

import { opens } from "@pinecall/core/scopes";
import type { SessionLine } from "@pinecall/core/wire/rest";
import type { HeldAgent } from "@pinecall/core/wire/rest-org";
import { whoOn } from "@pinecall/core/calls";

import { webVisitor } from "../lib/format";
import { AGENT_SCREENS, BOX_SCREENS, drawn, ORG_SCREENS, screensOf, WORLD, type Screen } from "../lib/mode";
import type { IconName } from "../ui";

export type Hit =
  /** A screen, drawn with its row's icon; `where` names the row a tab sits under, "" for a row. */
  | { kind: "screen"; group: string; icon: IconName; label: string; where: string; to: string }
  | { kind: "agent"; group: "Agents"; held: HeldAgent; to: string }
  | { kind: "call"; group: "Calls" | "Recent calls"; line: SessionLine; to: string };

/** A screen's icon: its own, or its row's when it is a tab. */
function iconOf(table: readonly Screen[], screen: Screen): IconName {
  if (screen.icon !== undefined) return screen.icon;
  return table.find((row) => row.key === screen.under)?.icon ?? "grid";
}

/** The row a tab sits under, by name; "" for a row of the sidebar. */
function rowOf(table: readonly Screen[], screen: Screen): string {
  return table.find((row) => row.key === screen.under)?.name ?? "";
}

/**
 * Every screen this console has that the key opens: an agent's under its own name, the org's, and
 * the box's for an operator. With an agent IN VIEW its screens come first, so "calls" lands on its
 * calls, and the org's row of the same name says "every agent" beside it; with every agent in
 * view the org's come first and `agent` (the first held, if any) is listed after, as a way in.
 */
export function screenHits({ scopes, billed, operator, agent, inView }: { scopes: readonly string[] | null; billed: boolean; operator: boolean; agent: string; inView: boolean }): Hit[] {
  const open = (key: string): boolean => scopes === null || opens(scopes, key);
  const own: Hit[] = [];
  if (agent !== "") {
    for (const screen of screensOf(AGENT_SCREENS).filter((one) => open(one.key))) {
      own.push({ kind: "screen", group: agent, icon: iconOf(AGENT_SCREENS, screen), label: screen.name, where: rowOf(AGENT_SCREENS, screen), to: `/a/${agent}/${screen.path}` });
    }
  }
  const named = new Set(inView ? own.map((hit) => hit.kind === "screen" && hit.label) : []);
  const orgs: Hit[] = [];
  for (const screen of drawn(screensOf(ORG_SCREENS), billed).filter((one) => open(one.key))) {
    const where = rowOf(ORG_SCREENS, screen);
    orgs.push({ kind: "screen", group: "Screens", icon: iconOf(ORG_SCREENS, screen), label: screen.name, where: where !== "" ? where : named.has(screen.name) ? "every agent" : "", to: `/${screen.path}` });
  }
  for (const screen of screensOf(BOX_SCREENS, WORLD, operator)) {
    orgs.push({ kind: "screen", group: "Box", icon: iconOf(BOX_SCREENS, screen), label: screen.name, where: rowOf(BOX_SCREENS, screen), to: `/${screen.path}` });
  }
  return inView ? [...own, ...orgs] : [...orgs, ...own];
}

export function agentHits(agents: readonly HeldAgent[]): Hit[] {
  return agents.map((held) => ({ kind: "agent", group: "Agents", held, to: `/a/${held.slug}/overview` }));
}

/** `base` is the calls screen a hit opens under: the org's, or the agent in view's, so the agent stays in view. */
export function callHits(lines: readonly SessionLine[], group: "Calls" | "Recent calls", base = "/calls"): Hit[] {
  return lines.map((line) => ({ kind: "call", group, line, to: `${base}/${line.call}` }));
}

/** The words a hit is found by: a screen's name and row, an agent's slug and channels, a call's id, parties, agent and outcome. */
export function saidBy(hit: Hit): string {
  switch (hit.kind) {
    case "screen":
      return `${hit.label} ${hit.where} ${hit.group}`;
    case "agent":
      return `${hit.held.slug} ${hit.held.channels.join(" ")} ${hit.held.kind}`;
    case "call":
      return [hit.line.call, whoOn(hit.line, webVisitor), hit.line.from, hit.line.to, hit.line.agent, hit.line.outcome, hit.line.channel].filter(Boolean).join(" ");
  }
}

/** The hits whose words contain what was typed, every word of it, in any order. */
export function matching(hits: readonly Hit[], query: string): Hit[] {
  const words = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  if (words.length === 0) return [...hits];
  return hits.filter((hit) => {
    const said = saidBy(hit).toLowerCase();
    return words.every((word) => said.includes(word));
  });
}
