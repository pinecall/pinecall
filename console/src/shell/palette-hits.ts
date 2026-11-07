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
 * Every screen this console has that the key opens: the org's, the box's for an operator, and
 * the agent in view's under its own name.
 */
export function screenHits({ scopes, billed, operator, agent }: { scopes: readonly string[] | null; billed: boolean; operator: boolean; agent: string }): Hit[] {
  const open = (key: string): boolean => scopes === null || opens(scopes, key);
  const hits: Hit[] = [];
  for (const screen of drawn(screensOf(ORG_SCREENS), billed).filter((one) => open(one.key))) {
    hits.push({ kind: "screen", group: "Screens", icon: iconOf(ORG_SCREENS, screen), label: screen.name, where: rowOf(ORG_SCREENS, screen), to: `/${screen.path}` });
  }
  for (const screen of screensOf(BOX_SCREENS, WORLD, operator)) {
    hits.push({ kind: "screen", group: "Box", icon: iconOf(BOX_SCREENS, screen), label: screen.name, where: rowOf(BOX_SCREENS, screen), to: `/${screen.path}` });
  }
  if (agent !== "") {
    for (const screen of screensOf(AGENT_SCREENS).filter((one) => open(one.key))) {
      hits.push({ kind: "screen", group: agent, icon: iconOf(AGENT_SCREENS, screen), label: screen.name, where: rowOf(AGENT_SCREENS, screen), to: `/a/${agent}/${screen.path}` });
    }
  }
  return hits;
}

export function agentHits(agents: readonly HeldAgent[]): Hit[] {
  return agents.map((held) => ({ kind: "agent", group: "Agents", held, to: `/a/${held.slug}/overview` }));
}

export function callHits(lines: readonly SessionLine[], group: "Calls" | "Recent calls"): Hit[] {
  return lines.map((line) => ({ kind: "call", group, line, to: `/calls/${line.call}` }));
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
