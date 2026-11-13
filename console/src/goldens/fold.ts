/** What the Goldens page draws, folded from what each agent's doors answer: the org's agents, each one's goldens with their last result, and how they stand. */

import type { HeldAgent } from "@pinecall/core/wire/rest-org";
import type { Hosted } from "../apps/door";
import type { EvalCase } from "../test/door";
import { goldensIn, inTheCode, resultsOf, saidIn, type Result } from "../test/fold";
import type { Read } from "./reads";

/** An agent of the org, and which of the two pages opens it: Apps for one written as code, Agents for one built in Studio. */
export interface Agent {
  slug: string;
  kind: "code" | "studio";
}

// An app is not an agent: one that holds its agents under other names (a voice app, `cloudacio-riley`
// holding `riley`) was listed by its own, and its goldens were asked of an agent nobody has.
/** Every agent connected or hosted, once each by name; `asked` is the one the address names, kept even when nobody holds it any more. */
export function agentsOf(held: readonly HeldAgent[], hosted: readonly Hosted[], asked: string): Agent[] {
  const studio = new Set([...held.filter((one) => one.kind === "studio").map((one) => one.slug), ...hosted.filter((one) => one.kind === "studio").map((one) => one.name)]);
  const theirs = hosted.flatMap((one) => (one.agents.length > 0 ? one.agents : [one.name]));
  const slugs = new Set([...held.map((one) => one.slug), ...theirs, ...(asked === "" ? [] : [asked])]);
  return [...slugs].sort().map((slug) => ({ slug, kind: studio.has(slug) ? "studio" : "code" }));
}

const named = encodeURIComponent;

/** The agent's Test tab, on the page of its kind. */
export const testTabOf = (agent: Agent): string => `${agent.kind === "studio" ? "/agents" : "/apps"}/${named(agent.slug)}/test`;

/** One golden open on this page. */
export const goldenPath = (agent: string, name: string): string => `/goldens/${named(agent)}/${named(name)}`;

/** A golden of an agent. `kept` is null for one that lives in the app's code: the gateway knows only how it stood in a run. */
export interface Row {
  name: string;
  kept: EvalCase | null;
  result: Result | undefined;
}

/** The agent's goldens: the cases a person approved or wrote, then the ones only a run of its code named. */
export function rowsOf(agent: Agent, read: Read): Row[] {
  const results = resultsOf(read.runs);
  const kept = goldensIn(read.cases).map((one): Row => ({ name: one.name, kept: one, result: results.get(one.name) }));
  // A Studio agent has no code: a golden a run played and the gateway keeps no case of was deleted since.
  const coded = agent.kind === "code" ? inTheCode(results, read.cases).map((name): Row => ({ name, kept: null, result: results.get(name) })) : [];
  return [...kept, ...coded];
}

export interface Tally {
  held: number;
  broke: number;
  none: number;
}

export function tallyOf(rows: readonly Row[]): Tally {
  const held = rows.filter((row) => row.result?.verdict === "held").length;
  const broke = rows.filter((row) => row.result?.verdict === "broke").length;
  return { held, broke, none: rows.length - held - broke };
}

/** Which goldens the list shows: every one, the ones that broke the last time, or the ones never played. */
export type Filter = "all" | "broke" | "none";

export function shownOf(rows: readonly Row[], filter: Filter, query: string): Row[] {
  const wanted = query.trim().toLowerCase();
  return rows.filter((row) => {
    if (filter === "broke" && row.result?.verdict !== "broke") return false;
    if (filter === "none" && row.result !== undefined) return false;
    if (wanted === "") return true;
    return [row.name, ...(row.kept === null ? [] : saidIn(row.kept.golden))].some((word) => word.toLowerCase().includes(wanted));
  });
}

/** The goldens Run all plays: the ones the gateway keeps that are not held out. */
export const playableIn = (rows: readonly Row[]): string[] => rows.filter((row) => row.kept !== null && !row.kept.held_out).map((row) => row.name);
