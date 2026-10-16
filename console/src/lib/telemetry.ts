/** Where the org sends its calls' traces (GET/PUT/DELETE /v1/telemetry), and the trace id a call's spans share. */

import { z } from "zod";

import { drop, put, read, type Credentials } from "@pinecall/core/api";

// runtime wire/rest/telemetry.py: TelemetryResponse; null when the org sends its traces nowhere.
const CollectorSchema = z.object({ endpoint: z.string(), header_names: z.array(z.string()), pii: z.boolean() });

/** The org's collector, as the gateway says it: the headers by name, never by value. */
export type Collector = z.infer<typeof CollectorSchema>;

const DOOR = "/v1/telemetry";

/** Where the org's traces go, or null. */
export async function readCollector(credentials: Credentials): Promise<Collector | null> {
  const answered: unknown = await read(credentials, DOOR);
  return answered === null ? null : CollectorSchema.parse(answered);
}

/** Set the collector, replacing the one the org had; the headers are sent once and never read back. */
export async function putCollector(credentials: Credentials, endpoint: string, headers: Record<string, string>, pii: boolean): Promise<void> {
  await put(credentials, DOOR, { endpoint, headers, pii });
}

/** Forget the collector: the traces stay on the platform alone. */
export async function dropCollector(credentials: Credentials): Promise<void> {
  await drop(credentials, DOOR);
}

// A call id of the gateway's own making: its 32 hex digits are the trace id as they stand
// (runtime worker/_traces.py trace_id_of); any other id hashes to one.
const A_HEX_CALL = /^call_([0-9a-f]{32})$/;

/** The trace id of a call's spans, as the worker gave it: the call id's hex, else SHA-256's first 32 hex digits. */
export async function traceIdOf(call: string): Promise<string> {
  const found = A_HEX_CALL.exec(call);
  if (found?.[1] !== undefined) return found[1];
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(call));
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("").slice(0, 32);
}
