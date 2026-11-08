/** What an app is, whichever way it reached the gateway: deployed here, held from a server of its own, or from somebody's terminal. */

import type { HeldAgent } from "@pinecall/core/wire/rest-org";
import type { Hosted } from "./door";

export type Mood = "good" | "warn" | "bad" | "calm";

export interface App {
  name: string;
  hosted: Hosted | null;
  held: HeldAgent | null;
}

export interface Said {
  state: string;
  mood: Mood;
  where: string;
}

/** One row per name, the stopped ones last: what the box hosts of that kind, and every agent of that kind that is connected. */
export function appsOf(hosted: readonly Hosted[], held: readonly HeldAgent[], kind: "code" | "studio"): App[] {
  const code = hosted.filter((one) => one.kind === kind);
  const classes = held.filter((one) => (one.kind === "studio") === (kind === "studio"));
  const named = new Set([...code.map((one) => one.name), ...classes.map((one) => one.slug)]);
  const apps = [...named].sort().map((name) => ({ name, hosted: code.find((one) => one.name === name) ?? null, held: classes.find((one) => one.slug === name) ?? null }));
  return [...apps.filter((one) => one.hosted?.stopped !== true), ...apps.filter((one) => one.hosted?.stopped === true)];
}

function terminalOf(held: HeldAgent): string | null {
  const holder = held.holder?.holder;
  return holder === undefined || holder === null || holder === "" ? null : `${held.holder?.name ?? "Somebody"}'s terminal`;
}

/** Its state, the newest release being the one a state speaks of, and where it runs. */
export function saidOf({ hosted, held }: App): Said {
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
