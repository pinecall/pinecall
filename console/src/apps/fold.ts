/** What an app is, whichever way it reached the gateway: deployed here, held from a server of its own, or from somebody's terminal. */

import type { HeldAgent } from "@pinecall/core/wire/rest-org";
import type { Hosted } from "./door";

export type Mood = "good" | "warn" | "bad" | "calm";

export interface App {
  name: string;
  hosted: Hosted | null;
  held: HeldAgent | null;
  /** The hosted app whose processes hold this agent, when the row is one of an app's agents; null on an app's own row. */
  of: string | null;
  /** The agents the app's processes hold under other names than its own: the rows listed under it, two or more. */
  agents: readonly string[];
  /** The agent this row's calls, tests, channels and settings are: its own name, or an app's one agent's. */
  agent: string;
}

export interface Said {
  state: string;
  mood: Mood;
  where: string;
}

// A voice app holds several agents under names that are not its own. Until 0.11.37 each of them was a row
// beside its app, "connected from your server": one app of two agents read as three apps. An app of one
// agent is that agent: one row, whose calls, tests and channels are the agent's.
/**
 * One row per app, the stopped ones last: what the box hosts of that kind, each followed by the agents its
 * processes hold when it holds several, and every other agent of that kind that is connected.
 */
export function appsOf(hosted: readonly Hosted[], held: readonly HeldAgent[], kind: "code" | "studio"): App[] {
  const code = hosted.filter((one) => one.kind === kind);
  const classes = held.filter((one) => (one.kind === "studio") === (kind === "studio"));
  const heldAs = (slug: string): HeldAgent | null => classes.find((one) => one.slug === slug) ?? null;
  const members = (app: Hosted): string[] => app.agents.filter((slug) => slug !== app.name).sort();
  const theirs = new Set(code.flatMap(members));
  const named = new Set([...code.map((one) => one.name), ...classes.map((one) => one.slug).filter((slug) => !theirs.has(slug))]);
  const apps = [...named].sort().map((name): App => {
    const app = code.find((one) => one.name === name) ?? null;
    const its = app === null ? [] : members(app);
    const only = its.length === 1 ? its[0] : undefined;
    if (only !== undefined) return { name, hosted: app, held: heldAs(only), of: null, agents: [], agent: only };
    return { name, hosted: app, held: heldAs(name), of: null, agents: its, agent: name };
  });
  const listed = [...apps.filter((one) => one.hosted?.stopped !== true), ...apps.filter((one) => one.hosted?.stopped === true)];
  return listed.flatMap((app) => [app, ...app.agents.map((slug): App => ({ name: slug, hosted: null, held: heldAs(slug), of: app.name, agents: [], agent: slug }))]);
}

/** Whether the row is an app whose calls are its agents': it holds agents, and none under its own name. */
export const isOfAgents = (app: App): boolean => app.agents.length > 0 && app.held === null;

function terminalOf(held: HeldAgent): string | null {
  const holder = held.holder?.holder;
  return holder === undefined || holder === null || holder === "" ? null : `${held.holder?.name ?? "Somebody"}'s terminal`;
}

/** Its state, the newest release being the one a state speaks of, and where it runs. */
export function saidOf({ hosted, held, of }: App): Said {
  if (of !== null) return { state: `Agent of ${of}`, mood: "good", where: "On Pinecall" };
  if (hosted !== null) {
    const where = hosted.kind === "studio" ? "Built in Studio" : "On Pinecall";
    if (hosted.stopped) return { state: "Stopped", mood: "calm", where };
    if (hosted.release === null) return { state: "No release yet", mood: "calm", where };
    if (hosted.failed_why !== null) return { state: `Release ${hosted.release} failed`, mood: "bad", where };
    if (hosted.live_release === hosted.release) return { state: `Live, release ${hosted.release}`, mood: "good", where };
    return { state: `Release ${hosted.release} on its way`, mood: "warn", where };
  }
  const terminal = held === null ? null : terminalOf(held);
  return terminal === null ? { state: "Connected", mood: "good", where: "Your server" } : { state: "Connected", mood: "warn", where: terminal };
}

export function hours(seconds: number): string {
  return `${(seconds / 3600).toFixed(1)} h`;
}

export function kilobytes(bytes: number): string {
  return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
