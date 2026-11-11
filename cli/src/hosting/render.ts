/** Hosting as a terminal reads it: a release sent and settled, the apps, the releases, the logs. */

import { date, formatHint, formatNotice } from "../kit/format.js";
import { table } from "../kit/table.js";
import type { HostedApp, Logs, Release, Sent, Settled } from "./service.js";

export const NO_APPS = "Pinecall hosts no app for this org here yet: `pinecall deploy` uploads this folder as one";

export function sent(one: Sent): string {
  const sent = `${one.name} · release ${one.release} sent · ${kilobytes(one.bytes)} · ${one.sha256.slice(0, 12)}`;
  return one.page === undefined ? sent : `${sent}\n${formatHint(`its page: ${one.page}`)}`;
}

export function rolledBack(one: Sent, from: number): string {
  return `${one.name} · release ${from}'s sources sent again as release ${one.release}`;
}

export const FOLLOWING = "  installing · the release before keeps answering meanwhile";

export function settled(said: Settled | null, release: number, withinMs: number): string[] {
  if (said === null) return [`  release ${release} is not live after ${Math.round(withinMs / 1000)}s`, formatHint("pinecall deploy list says where it is")];
  return [said.line, formatHint(said.live ? "pinecall deploy logs reads its lines" : "pinecall deploy logs reads why")];
}

/** The org's hosted apps as a table: the name, the release live, and the one on its way or that failed. */
export function apps(found: HostedApp[]): string[] {
  if (found.length === 0) return formatNotice(NO_APPS);
  return table(["app", "live", "newest"], found.map((app) => [app.name, liveOf(app), newestOf(app)]));
}

/** The app's releases as a table: number, when, size, who sent it, the note. */
export function releases(found: Release[]): string[] {
  const noted = found.some((one) => one.note !== "");
  return table(["release", "when", "size", "by", ...(noted ? ["note"] : [])], found.map((one) => [one.release, date(one.created_at), kilobytes(one.bytes), one.author, ...(noted ? [one.note || "—"] : [])]));
}

export function stopped({ name }: { name: string }): string {
  return `${name} · stopped: its process drains, its releases and token stay`;
}

export function started({ name }: { name: string }): string[] {
  return [`${name} · started: its newest release answers once its agents register`, formatHint("pinecall deploy list says when")];
}

export function removed({ name }: { name: string }): string {
  return `${name} · no longer hosted, its token revoked`;
}

export const KEPT = (name: string): string => `${name} stays hosted: nothing removed`;

/** The app's lines, said stale or missing first when they are. */
export function logs(found: Logs): string[] {
  if (found.none) return formatNotice(`Pinecall has no lines of ${found.name} yet: \`pinecall deploy list\` says whether it runs`);
  const lines = found.lines.replace(/\n$/, "").split("\n");
  return found.staleBy === null ? lines : [`${found.name}: Pinecall sent nothing new; these are its lines from ${found.staleBy}s ago`, ...lines];
}

function liveOf(app: HostedApp): string {
  if (app.stopped) return "stopped";
  return app.live_release === null ? "—" : `release ${app.live_release}`;
}

// The newest release when it is not the live one: on its way, or failed with the first thing it said.
function newestOf(app: HostedApp): string {
  if (app.release === null) return "no release yet";
  if (app.live_release === app.release && !app.stopped) return "—";
  if (app.failed_why !== null) return `release ${app.release} failed: ${whyOf(app.failed_why)}`;
  return app.stopped ? `release ${app.release}` : `release ${app.release} on its way`;
}

// The first line that says something, its trailing colon gone: what follows it is the process's own output.
function whyOf(failed: string): string {
  const first = failed.split("\n").map((line) => line.trim()).find((line) => line !== "") ?? "";
  return first.replace(/:$/, "");
}

function kilobytes(bytes: number): string {
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}
