/** Hosting as a terminal reads it: a release sent and settled, the apps, the releases, the logs. */

import { date } from "../kit/format.js";
import type { HostedApp, Logs, Release, Sent, Settled } from "./service.js";

export const NO_APPS = "Pinecall hosts no app for this org here yet: `pinecall deploy` uploads this folder as one";

export function sent(one: Sent): string {
  return `${one.name}: release ${one.release} sent · ${kilobytes(one.bytes)} · ${one.sha256.slice(0, 12)}`;
}

export function rolledBack(one: Sent, from: number): string {
  return `${one.name}: release ${from}'s sources sent again as release ${one.release}`;
}

export function following(name: string): string {
  return `${name}: Pinecall installs and starts it; the release before keeps answering meanwhile`;
}

export function settled(said: Settled | null, release: number, withinMs: number): string {
  return said?.line ?? `release ${release} is not live after ${Math.round(withinMs / 1000)}s: \`pinecall deploy list\` says where it is`;
}

export function apps(found: HostedApp[]): string[] {
  if (found.length === 0) return [NO_APPS];
  const wide = Math.max(...found.map((app) => app.name.length));
  return found.map((app) => `${app.name.padEnd(wide)}  ${stateOf(app)}`);
}

export function releases(found: Release[]): string[] {
  return found.map((one) => `${String(one.release).padStart(4)}  ${date(one.created_at)}  ${kilobytes(one.bytes).padStart(8)}  ${one.author}${one.note === "" ? "" : `  ${one.note}`}`);
}

export function stopped({ name }: { name: string }): string {
  return `${name}: stopped — its process drains; its releases and token stay`;
}

export function started({ name }: { name: string }): string {
  return `${name}: started — its newest release answers once its agents register (\`pinecall deploy list\`)`;
}

export function removed({ name }: { name: string }): string {
  return `${name}: no longer hosted, its token revoked`;
}

/** The app's lines, said stale or missing first when they are. */
export function logs(found: Logs): string[] {
  if (found.none) return [`${found.name}: Pinecall sent no lines yet — is it running? \`pinecall deploy list\` says`];
  const lines = found.lines.replace(/\n$/, "").split("\n");
  return found.staleBy === null ? lines : [`${found.name}: Pinecall sent nothing new; these are its lines from ${found.staleBy}s ago`, ...lines];
}

function stateOf(app: HostedApp): string {
  if (app.stopped) return `stopped${app.release === null ? "" : ` · newest release ${app.release}`}`;
  if (app.release === null) return "no release yet";
  const serving = app.live_release === null ? "nothing live" : `live: release ${app.live_release}`;
  if (app.failed_why !== null) return `${serving} · release ${app.release} failed: ${app.failed_why.split("\n")[0]}`;
  if (app.live_release === app.release) return serving;
  return `${serving} · release ${app.release} on its way`;
}

function kilobytes(bytes: number): string {
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}
