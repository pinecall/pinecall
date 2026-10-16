/** What an app's row says: its state in one line, the hours it served this month, how fresh its logs are. */

import type { Hosted, Served } from "./door";

/** An app's state, as the row's pill says it. */
export interface AppState {
  text: string;
  tone: "green" | "amber" | "red" | "gray";
  /** Why the newest release failed, whole; null unless it did. */
  why: string | null;
}

/** Stopped, live, on its way, or failed — the newest release is the one a state speaks of. */
export function stateOf(app: Hosted): AppState {
  if (app.stopped) return { text: "stopped", tone: "gray", why: null };
  if (app.release === null) return { text: "no release yet", tone: "gray", why: null };
  if (app.failed_why !== null) return { text: `release ${app.release} failed`, tone: "red", why: app.failed_why };
  if (app.live_release === app.release) return { text: `live · release ${app.release}`, tone: "green", why: null };
  return { text: `release ${app.release} on its way`, tone: "amber", why: null };
}

/** The first line of a failure, what the row shows before it is opened. */
export function firstLine(why: string): string {
  return why.trim().split("\n")[0] ?? "";
}

/** The seconds each app served, summed over the days of the page. */
export function servedByApp(rows: readonly Served[]): Map<string, number> {
  const served = new Map<string, number>();
  for (const row of rows) served.set(row.name, (served.get(row.name) ?? 0) + row.seconds);
  return served;
}

/** Seconds as hours, one decimal: `12.5 h`. */
export function hours(seconds: number): string {
  return `${(seconds / 3600).toFixed(1)} h`;
}

/** How fresh the lines are: `read 4 s ago`, or the box still being asked. */
export function readAgo(at: number | null, now: number = Date.now() / 1000): string {
  if (at === null) return "asking the box for its lines…";
  return `read ${Math.max(0, Math.round(now - at))} s ago`;
}
