/** Hosting: the project uploaded as a release Pinecall installs and runs, followed until live; the apps, their releases, logs, rollback, stop and start. */

import { existsSync, readFileSync } from "node:fs";
import { basename, join, relative } from "node:path";

import * as api from "../api/hosting.js";
import type { Context } from "../context.js";
import { UsageError } from "../errors.js";
import { projectFiles, tarball } from "../kit/tarball.js";
import { agentFilesOf } from "../project/layout.js";
import { languageOf } from "../project/language.js";

export type { AppLogs, HostedApp, Release } from "../api/hosting.js";

export const A_SLUG = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

// The runner beats every five seconds, installs within five minutes and waits two for a register.
export const FOLLOW_WITHIN_MS = 8 * 60 * 1000;
// A fresh read of an app's lines is a beat or two away.
export const LOGS_WITHIN_MS = 15_000;
// Pinecall installs the project and serves the agent through the framework the project pinned.
const SERVED_BY = ["@pinecall/agents"] as const;

export const NOT_A_NAME = (name: string): string => `${name} is no name for an app: lower-case letters and digits joined by dashes — pass --name support`;
export const NOTHING_TO_SEND = "nothing to send: this folder holds no file a release would carry";
export const NOT_SERVABLE = (missing: readonly string[]): string =>
  `Pinecall serves this project through its own ${missing.join(" and ")}, and its package.json does not list ${missing.join(" or ")} in dependencies: npm i ${missing.join(" ")}`;
export const NOT_HOSTED = (file: string): string => `Pinecall hosts TypeScript projects, and ${file} is not one: run \`pinecall start\` on a server of your own, with a server's token in PINECALL_KEY`;

/** A release sent: the app, its number, its size and hash. */
export interface Sent {
  name: string;
  release: number;
  bytes: number;
  sha256: string;
}

/** How a release stands once it is settled: live, failed or replaced. Null when the wait ran out first. */
export interface Settled {
  live: boolean;
  line: string;
}

/** An app's last lines: fresh, stale (with how long ago), or none yet. */
export interface Logs {
  name: string;
  lines: string;
  staleBy: number | null;
  none: boolean;
}

/** The app a verb acts on: the one named, else the project folder's name. */
export function appName(ctx: Context, name?: string): string {
  const found = name ?? basename(ctx.cwd).toLowerCase();
  if (!A_SLUG.test(found)) throw new UsageError(NOT_A_NAME(found));
  return found;
}

export async function listApps(ctx: Context): Promise<api.HostedApp[]> {
  return api.listApps(ctx.gateway());
}

export async function listReleases(ctx: Context, name: string): Promise<api.Release[]> {
  return api.listReleases(ctx.gateway(), name);
}

/**
 * This folder uploaded as the app's next release: every file its .gitignore files leave in, never
 * node_modules, .git, dist or any .env. Refused before anything is sent when the project is not
 * TypeScript, does not depend on the framework, or holds nothing to send.
 */
export async function uploadRelease(ctx: Context, name: string, note: string): Promise<Sent> {
  const foreign = agentFilesOf(ctx.cwd).find((file) => languageOf(file) !== "typescript");
  if (foreign !== undefined) throw new UsageError(NOT_HOSTED(relative(ctx.cwd, foreign)));
  const missing = notDependedOn(ctx.cwd);
  if (missing.length > 0) throw new UsageError(NOT_SERVABLE(missing));
  const files = projectFiles(ctx.cwd);
  if (files.length === 0) throw new UsageError(NOTHING_TO_SEND);
  const sent = await api.uploadRelease(ctx.gateway(), name, tarball(ctx.cwd, files), note);
  return { name: sent.name, release: sent.release, bytes: sent.bytes, sha256: sent.sha256 };
}

/** Release n's sources kept again as the next release. */
export async function rollbackRelease(ctx: Context, name: string, release: number): Promise<Sent> {
  if (!Number.isInteger(release) || release < 1) throw new UsageError(`rollback ${release}: a release is its number, from \`pinecall deploy releases\``);
  const again = await api.rollbackRelease(ctx.gateway(), name, release);
  return { name: again.name, release: again.release, bytes: again.bytes, sha256: again.sha256 };
}

export async function stopApp(ctx: Context, name: string): Promise<{ name: string }> {
  await api.stopApp(ctx.gateway(), name);
  return { name };
}

export async function startApp(ctx: Context, name: string): Promise<{ name: string }> {
  await api.startApp(ctx.gateway(), name);
  return { name };
}

/** Stop hosting the app: its releases go, and its token is revoked. */
export async function removeApp(ctx: Context, name: string): Promise<{ name: string }> {
  await api.deleteApp(ctx.gateway(), name);
  return { name };
}

/**
 * How the release stands once it is settled (live, failed, replaced), read when the org's feed says
 * the app changed and each time a stream opens; null when `withinMs` passes first.
 */
export async function followRelease(ctx: Context, name: string, release: number, withinMs: number): Promise<Settled | null> {
  const stop = new AbortController();
  const late = setTimeout(() => stop.abort(), withinMs);
  const read = async (): Promise<Settled | undefined> => {
    const app = (await api.listApps(ctx.gateway())).find((one) => one.name === name);
    return app === undefined ? undefined : standingOf(app, release);
  };
  // One read at a time, in the order the feed spoke; the stream opening (and reopening) is a reason to read too.
  let found: Settled | null = null;
  let reading = Promise.resolve();
  const look = (): void => {
    reading = reading.then(async () => {
      if (found !== null) return;
      found = (await read()) ?? null;
      if (found !== null) stop.abort();
    });
  };
  try {
    for await (const changed of api.streamReleaseChanges(ctx.gateway(), look, stop.signal)) if (changed === name) look();
  } catch (failed) {
    if (!stop.signal.aborted) throw failed;
  } finally {
    clearTimeout(late);
    stop.abort();
    await reading.catch(() => undefined);
  }
  return found;
}

/** A release's standing on its app, or undefined while it is still on its way. */
export function standingOf(app: api.HostedApp, ours: number): Settled | undefined {
  if (app.live_release === ours) return { live: true, line: `${app.name}: release ${ours} is live` };
  if (app.release !== null && app.release > ours) return { live: false, line: `release ${ours} was replaced by release ${app.release} before it went live` };
  if (app.release === ours && app.failed_why !== null) {
    const before = app.live_release === null ? "nothing was serving before it" : `release ${app.live_release} keeps serving`;
    return { live: false, line: `${app.name}: release ${ours} failed — ${before}\n${app.failed_why}` };
  }
  return undefined;
}

/** What a follow of the logs is told: the first read when it is settled, and every line that comes after it. */
export interface LogListeners {
  onFirst: (first: Logs) => void;
  onMore: (lines: string[]) => void;
}

/**
 * The app's last lines. Asking is what makes Pinecall's runner send them, on its next beat: the
 * stream's first frame is what it sent last. Lines read after this ask are waited for; past
 * `withinMs`, what there is, said stale. With listeners, the first read is said as it settles and
 * what comes after is handed on, until `signal` aborts.
 */
export async function readLogs(ctx: Context, name: string, withinMs: number, follow?: LogListeners, signal?: AbortSignal): Promise<Logs> {
  const askedAt = Date.now() / 1000;
  const stop = new AbortController();
  signal?.addEventListener("abort", () => stop.abort(), { once: true });
  let last: api.AppLogs = { name, host: null, lines: "", at: null };
  let first: Logs | undefined;
  const settle = (): Logs => {
    first = { name, lines: last.lines, staleBy: last.at !== null && last.at < askedAt ? Math.round(askedAt - last.at) : null, none: last.at === null && last.lines === "" };
    if (follow === undefined) stop.abort();
    else follow.onFirst(first);
    return first;
  };
  const deadline = setTimeout(() => first ?? settle(), withinMs);
  try {
    for await (const read of api.streamLogs(ctx.gateway(), name, stop.signal)) {
      if (first === undefined) {
        last = read;
        if (read.at !== null && read.at >= askedAt) settle();
        continue;
      }
      if (read.at === null || read.at === last.at) continue;
      const added = newLines(last.lines, read.lines);
      if (added.length > 0) follow?.onMore(added);
      last = read;
    }
  } catch (failed) {
    if (!stop.signal.aborted) throw failed;
  } finally {
    clearTimeout(deadline);
  }
  return first ?? settle();
}

/** The lines after the part two reads share: what a follow prints of a newer read. */
export function newLines(before: string, after: string): string[] {
  const old = before.split("\n").filter((line) => line !== "");
  const now = after.split("\n").filter((line) => line !== "");
  for (let shared = Math.min(old.length, now.length); shared > 0; shared -= 1) {
    if (old.slice(old.length - shared).every((line, at) => line === now[at])) return now.slice(shared);
  }
  return now;
}

function notDependedOn(cwd: string): string[] {
  const manifest = join(cwd, "package.json");
  const listed = existsSync(manifest) ? ((JSON.parse(readFileSync(manifest, "utf8")) as { dependencies?: Record<string, string> }).dependencies ?? {}) : {};
  return SERVED_BY.filter((name) => !(name in listed));
}
