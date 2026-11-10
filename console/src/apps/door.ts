/** The apps doors: what the box hosts for the org, its releases and logs, what a person does to one, and the secrets apps start with. */

import { z } from "zod";

import { drop, post, put, read, type Credentials } from "@pinecall/core/api";

const HostedSchema = z.object({
  name: z.string(),
  release: z.number().int().nullable(),
  live_release: z.number().int().nullable(),
  failed_why: z.string().nullable(),
  stopped: z.boolean(),
  kind: z.enum(["code", "studio"]),
  created_by: z.string(),
  created_at: z.number(),
});

const ReleaseSchema = z.object({ name: z.string(), release: z.number().int(), sha256: z.string(), bytes: z.number().int(), author: z.string(), note: z.string(), created_at: z.number() });
const LogsSchema = z.object({ name: z.string(), host: z.string().nullable(), lines: z.string(), at: z.number().nullable() });
const ServedSchema = z.object({ name: z.string(), day: z.string(), seconds: z.number() }).loose();
const SecretSchema = z.object({ name: z.string(), set_by: z.string(), set_at: z.number() });
const SecretsSchema = z.object({ secrets: z.array(SecretSchema) });

export type Hosted = z.infer<typeof HostedSchema>;
export type Release = z.infer<typeof ReleaseSchema>;
export type Logs = z.infer<typeof LogsSchema>;
export type Secret = z.infer<typeof SecretSchema>;

const doorOf = (name: string): string => `/v1/hosted/${encodeURIComponent(name)}`;
const secretDoor = (name: string): string => `/v1/secrets/${encodeURIComponent(name)}`;

/** Who a deploy names: a teammate's name for their member id; a key's own label is said as it is. */
export function whoIs(names: ReadonlyMap<string, string>, id: string): string {
  return names.get(id) ?? (id.startsWith("m_") ? "A teammate" : id);
}

export async function readHosted(credentials: Credentials): Promise<Hosted[]> {
  return z.object({ apps: z.array(HostedSchema) }).parse(await read(credentials, "/v1/hosted")).apps;
}

/** The seconds each app served this month. */
export async function readServed(credentials: Credentials): Promise<Map<string, number>> {
  const { rows } = z.object({ rows: z.array(ServedSchema) }).parse(await read(credentials, "/v1/hosted/usage"));
  const served = new Map<string, number>();
  for (const row of rows) served.set(row.name, (served.get(row.name) ?? 0) + row.seconds);
  return served;
}

export async function readReleases(credentials: Credentials, name: string): Promise<Release[]> {
  return z.object({ releases: z.array(ReleaseSchema) }).parse(await read(credentials, `${doorOf(name)}/releases`)).releases;
}

export async function rollBack(credentials: Credentials, name: string, release: number): Promise<Release> {
  return ReleaseSchema.parse(await post(credentials, `${doorOf(name)}/rollback`, { release }));
}

export async function stopApp(credentials: Credentials, name: string): Promise<void> {
  await post(credentials, `${doorOf(name)}/stop`, {});
}

export async function startApp(credentials: Credentials, name: string): Promise<void> {
  await post(credentials, `${doorOf(name)}/start`, {});
}

export async function removeApp(credentials: Credentials, name: string): Promise<void> {
  await drop(credentials, doorOf(name));
}

/** The path of an app's logs, which streams the lines when asked for `text/event-stream`. */
export const logsPath = (name: string): string => `${doorOf(name)}/logs`;

export function logsIn(frame: string): Logs {
  return LogsSchema.parse(JSON.parse(frame));
}

export async function readSecrets(credentials: Credentials): Promise<Secret[]> {
  return SecretsSchema.parse(await read(credentials, "/v1/secrets")).secrets;
}

export async function putSecret(credentials: Credentials, name: string, value: string): Promise<Secret[]> {
  return SecretsSchema.parse(await put(credentials, secretDoor(name), { value })).secrets;
}

export async function dropSecret(credentials: Credentials, name: string): Promise<Secret[]> {
  return SecretsSchema.parse(await drop(credentials, secretDoor(name))).secrets;
}
