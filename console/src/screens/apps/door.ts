/** Apps screen API: the org's hosted apps, their releases, logs and time served, and what a person does to one. */

import { z } from "zod";

import { drop, post, read, type Credentials } from "@pinecall/core/api";

// runtime wire/rest/hosting.py: HostedAppRow. `release` is the newest, `live_release` the one
// serving, `failed_why` why the newest did not build or start.
const HostedSchema = z.object({
  name: z.string(),
  release: z.number().int().nullable(),
  live_release: z.number().int().nullable(),
  failed_why: z.string().nullable(),
  stopped: z.boolean(),
  created_by: z.string(),
  created_at: z.number(),
});

// runtime wire/rest/hosting.py: ReleaseRow.
const ReleaseSchema = z.object({
  name: z.string(),
  release: z.number().int(),
  sha256: z.string(),
  bytes: z.number().int(),
  author: z.string(),
  note: z.string(),
  created_at: z.number(),
});

// runtime wire/rest/hosting.py: AppLogsResponse. `at` is null until the runner has sent any.
const LogsSchema = z.object({
  name: z.string(),
  host: z.string().nullable(),
  lines: z.string(),
  at: z.number().nullable(),
});

// runtime wire/rest/hosting.py: ServedRow and ServedPage.
const ServedSchema = z.object({
  org: z.string(),
  env: z.enum(["production", "sandbox"]),
  name: z.string(),
  day: z.string(),
  seconds: z.number(),
});

const ServedPageSchema = z.object({ since: z.string(), until: z.string(), rows: z.array(ServedSchema) });

/** One app the box hosts for the org in this world. */
export type Hosted = z.infer<typeof HostedSchema>;

/** One release of a hosted app. */
export type Release = z.infer<typeof ReleaseSchema>;

/** The last lines the runner read of an app's process. */
export type Logs = z.infer<typeof LogsSchema>;

/** The time one app served on one UTC day. */
export type Served = z.infer<typeof ServedSchema>;

const doorOf = (name: string): string => `/v1/hosted/${encodeURIComponent(name)}`;

/** The org's hosted apps in this world, by name. */
export async function readHosted(credentials: Credentials): Promise<Hosted[]> {
  return z.object({ apps: z.array(HostedSchema) }).parse(await read(credentials, "/v1/hosted")).apps;
}

/** An app's releases, newest first. */
export async function readReleases(credentials: Credentials, name: string): Promise<Release[]> {
  return z.object({ releases: z.array(ReleaseSchema) }).parse(await read(credentials, `${doorOf(name)}/releases`)).releases;
}

/** An earlier release's sources kept again as the app's next release, which it answers. */
export async function rollBack(credentials: Credentials, name: string, release: number): Promise<Release> {
  return ReleaseSchema.parse(await post(credentials, `${doorOf(name)}/rollback`, { release }));
}

/** Stop running the app: its process drains, and its releases and token stay. */
export async function stopApp(credentials: Credentials, name: string): Promise<void> {
  await post(credentials, `${doorOf(name)}/stop`, {});
}

/** Run a stopped app again, its newest release. */
export async function startApp(credentials: Credentials, name: string): Promise<void> {
  await post(credentials, `${doorOf(name)}/start`, {});
}

/** Remove the app: its releases go and its token is revoked. */
export async function removeApp(credentials: Credentials, name: string): Promise<void> {
  await drop(credentials, doorOf(name));
}

/** The app's last lines; asking is also what makes the runner send fresh ones with its next beat. */
export async function readLogs(credentials: Credentials, name: string): Promise<Logs> {
  return LogsSchema.parse(await read(credentials, `${doorOf(name)}/logs`));
}

/** The path of the app's logs, which streams the lines when asked for `text/event-stream`. */
export const logsPath = (name: string): string => `${doorOf(name)}/logs`;

/** One `app.logs` frame of that stream: the same body the door answers. */
export function logsIn(frame: string): Logs {
  return LogsSchema.parse(JSON.parse(frame));
}

/** The time the org's apps served per UTC day this month, in this world. */
export async function readServed(credentials: Credentials): Promise<Served[]> {
  return ServedPageSchema.parse(await read(credentials, "/v1/hosted/usage")).rows;
}
