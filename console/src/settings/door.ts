/** Settings' doors: the org's keys listed, made and revoked; the vendors it runs on and its own credentials for them; and the collector its traces go to. */

import { z } from "zod";

import { drop, post, put, read, type Credentials } from "@pinecall/core/api";

const named = encodeURIComponent;

// ── keys ──

const KeySchema = z.looseObject({
  fingerprint: z.string(),
  label: z.string().nullable(),
  /** A person's own key, made at each sign-in; or a server's token, the org's. */
  kind: z.enum(["person", "server"]),
  env: z.enum(["production", "sandbox"]).nullable(),
  name: z.string().nullable(),
  created_at: z.string(),
  last_used_at: z.string().nullable(),
  revoked_at: z.string().nullable(),
  scopes: z.array(z.string()),
});
export type Key = z.infer<typeof KeySchema>;

/** The one answer that carries a key in the clear: shown once and kept nowhere. */
const IssuedSchema = z.looseObject({ key: z.string(), label: z.string().nullable(), env: z.string() });
export type Issued = z.infer<typeof IssuedSchema>;

export async function readKeys(credentials: Credentials): Promise<Key[]> {
  return z.array(KeySchema).parse(await read(credentials, "/v1/keys"));
}

/** A server's token for the org in one environment. */
export async function makeKey(credentials: Credentials, wanted: { label: string; env: "production" | "sandbox" }): Promise<Issued> {
  return IssuedSchema.parse(await post(credentials, "/v1/keys", wanted));
}

/** Stop a key from the next request on; its row and what it did are kept. */
export async function revokeKey(credentials: Credentials, fingerprint: string): Promise<void> {
  await post(credentials, `/v1/keys/${named(fingerprint)}/revoke`, {});
}

// ── vendors ──

const VendorSchema = z.looseObject({
  name: z.string(),
  /** The stages it runs: stt, llm, tts. */
  does: z.array(z.string()),
  /** How this org may run it: on its own key, on the platform's, or only by bringing one. */
  availability: z.string().optional(),
  broken: z.string().nullish(),
});
export type Vendor = z.infer<typeof VendorSchema>;

export async function readVendors(credentials: Credentials): Promise<Vendor[]> {
  return z.looseObject({ providers: z.array(VendorSchema) }).parse(await read(credentials, "/v1/providers")).providers;
}

/** Keep the org's own credentials for a vendor: its calls run on them from the next one. */
export async function keepVendorKey(credentials: Credentials, vendor: string, key: string): Promise<void> {
  await put(credentials, `/v1/provider-keys/${named(vendor)}`, { key });
}

/** Forget them: its calls run on the platform's from the next one, where it lends that vendor. */
export async function dropVendorKey(credentials: Credentials, vendor: string): Promise<void> {
  await drop(credentials, `/v1/provider-keys/${named(vendor)}`);
}

// ── traces ──

const CollectorSchema = z.looseObject({ endpoint: z.string(), header_names: z.array(z.string()), pii: z.boolean() });
export type Collector = z.infer<typeof CollectorSchema>;

/** Where the org's calls' traces go, and which headers are set, never their values; null when nowhere of its own. */
export async function readCollector(credentials: Credentials): Promise<Collector | null> {
  const answered = await read(credentials, "/v1/telemetry");
  return answered === null ? null : CollectorSchema.parse(answered);
}

export async function keepCollector(credentials: Credentials, wanted: { endpoint: string; headers: Record<string, string>; pii: boolean }): Promise<void> {
  await put(credentials, "/v1/telemetry", wanted);
}

export async function dropCollector(credentials: Credentials): Promise<void> {
  await drop(credentials, "/v1/telemetry");
}
