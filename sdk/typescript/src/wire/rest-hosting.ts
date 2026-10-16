/** The hosting doors: the apps the box runs for an org, their releases, and the org's secrets. */

import { z } from "zod";

/** A row of GET /v1/hosted: an app, its newest release, the one serving, and why the newest failed. */
export const HostedAppSchema = z.strictObject({
  name: z.string(),
  release: z.int().nullable(),
  live_release: z.int().nullable(),
  failed_why: z.string().nullable(),
  stopped: z.boolean(),
  created_by: z.string(),
  created_at: z.number(),
});

export type HostedApp = z.infer<typeof HostedAppSchema>;

/** GET /v1/hosted. */
export const HostedAppListSchema = z.strictObject({ apps: z.array(HostedAppSchema) });

export type HostedAppList = z.infer<typeof HostedAppListSchema>;

/** What POST /v1/hosted/{name}/releases answers, and a row of GET …/releases. */
export const ReleaseSchema = z.strictObject({
  name: z.string(),
  release: z.int(),
  sha256: z.string(),
  bytes: z.int(),
  author: z.string(),
  note: z.string(),
  created_at: z.number(),
});

export type Release = z.infer<typeof ReleaseSchema>;

/** GET /v1/hosted/{name}/releases: newest first. */
export const ReleaseListSchema = z.strictObject({ releases: z.array(ReleaseSchema) });

export type ReleaseList = z.infer<typeof ReleaseListSchema>;

/** GET /v1/hosted/{name}/logs: the last lines the runner read; `at` null before it sent any. */
export const AppLogsSchema = z.strictObject({
  name: z.string(),
  host: z.string().nullable(),
  lines: z.string(),
  at: z.number().nullable(),
});

export type AppLogs = z.infer<typeof AppLogsSchema>;

/** A row of GET /v1/secrets: never a value. */
export const SecretRowSchema = z.strictObject({ name: z.string(), set_by: z.string(), set_at: z.number() });

/** GET /v1/secrets, and what PUT and DELETE answer. */
export const SecretListSchema = z.strictObject({ secrets: z.array(SecretRowSchema) });

export type SecretList = z.infer<typeof SecretListSchema>;
