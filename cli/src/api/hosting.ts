/** The hosting endpoints: the org's hosted apps, their releases, an app's logs, and the feed's release changes. */

import { observe, sseFrames } from "@pinecall/agents/client";
import type { AppLogs, HostedApp, HostedAppList, Release, ReleaseList } from "@pinecall/agents/wire";

import { seg, type GatewayClient } from "./client.js";

export type { AppLogs, HostedApp, Release } from "@pinecall/agents/wire";

/** The feed's entry type for a release that moved: uploaded, live, failed or replaced. */
const RELEASE_CHANGED = "release.changed";

// A note longer than this is cut: the gateway keeps it as a line, not a page.
const NOTE_LENGTH = 200;

function appPath(name: string): string {
  return `/v1/hosted/${seg(name)}`;
}

export async function listApps(gw: GatewayClient): Promise<HostedApp[]> {
  return (await gw.get<HostedAppList>("/v1/hosted")).apps;
}

export async function listReleases(gw: GatewayClient, name: string): Promise<Release[]> {
  return (await gw.get<ReleaseList>(`${appPath(name)}/releases`)).releases;
}

/** `POST /v1/hosted/{name}/releases`: the body is the gzipped tarball itself, never JSON. */
export function uploadRelease(gw: GatewayClient, name: string, source: Buffer, note: string): Promise<Release> {
  return gw.request<Release>(`${appPath(name)}/releases`, {
    method: "POST",
    body: source,
    query: { note: note === "" ? undefined : note.slice(0, NOTE_LENGTH) },
    headers: { "content-type": "application/gzip" },
  });
}

/** `POST /v1/hosted/{name}/rollback`: release n's sources kept again as the next release. */
export function rollbackRelease(gw: GatewayClient, name: string, release: number): Promise<Release> {
  return gw.post<Release>(`${appPath(name)}/rollback`, { release });
}

export async function stopApp(gw: GatewayClient, name: string): Promise<void> {
  await gw.post(`${appPath(name)}/stop`);
}

export async function startApp(gw: GatewayClient, name: string): Promise<void> {
  await gw.post(`${appPath(name)}/start`);
}

export async function deleteApp(gw: GatewayClient, name: string): Promise<void> {
  await gw.delete(appPath(name));
}

/**
 * `GET /v1/hosted/{name}/logs` as SSE: one frame per read the runner sends, the first being its
 * last read; reconnects by itself until `signal` aborts.
 */
export async function* streamLogs(gw: GatewayClient, name: string, signal: AbortSignal): AsyncGenerator<AppLogs> {
  for await (const frame of sseFrames(gw.urlOf(`${appPath(name)}/logs`), { apiKey: gw.key, env: gw.env, signal })) {
    if (frame.data !== "") yield JSON.parse(frame.data) as AppLogs;
  }
}

/**
 * The name of each app whose release moved, from the org's feed (`release.changed` alone), until
 * `signal` aborts. `onOpen` is said each time the stream opens, the first and every reconnect:
 * what moved while it was down was never said.
 */
export async function* streamReleaseChanges(gw: GatewayClient, onOpen: () => void, signal: AbortSignal): AsyncGenerator<string> {
  const options = { url: gw.url, apiKey: gw.key, env: gw.env, types: [RELEASE_CHANGED], onOpen, signal };
  for await (const { entry } of observe({ feed: true }, options)) {
    const app = (entry.data as Record<string, unknown>)["app"];
    if (typeof app === "string") yield app;
  }
}
