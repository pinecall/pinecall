/** Where the org sends its calls' traces (GET, PUT and DELETE /v1/telemetry), and how Langfuse is said as such a collector. */

import { z } from "zod";

import { drop, put, read, type Credentials } from "@pinecall/core/api";

// runtime wire/rest/telemetry.py: TelemetryResponse; null when the org sends its traces nowhere.
const CollectorSchema = z.object({ endpoint: z.string(), header_names: z.array(z.string()), pii: z.boolean() });

/** The org's collector as the gateway says it: the headers by name, never by value. */
export type Collector = z.infer<typeof CollectorSchema>;

/** What a form asks to keep: the headers are sent once and never read back. */
export interface Wanted {
  endpoint: string;
  headers: Record<string, string>;
  pii: boolean;
}

const DOOR = "/v1/telemetry";

export async function readCollector(credentials: Credentials): Promise<Collector | null> {
  const answered: unknown = await read(credentials, DOOR);
  return answered === null ? null : CollectorSchema.parse(answered);
}

/** Set the collector, replacing the one the org had. */
export async function putCollector(credentials: Credentials, wanted: Wanted): Promise<void> {
  await put(credentials, DOOR, wanted);
}

/** Forget the collector: the traces stay on the platform alone. */
export async function dropCollector(credentials: Credentials): Promise<void> {
  await drop(credentials, DOOR);
}

// Langfuse takes OpenTelemetry over HTTP at /api/public/otel (langfuse.com/integrations/native/opentelemetry).
export const LANGFUSE_REGIONS: readonly { value: string; label: string; base: string }[] = [
  { value: "eu", label: "EU", base: "https://cloud.langfuse.com" },
  { value: "us", label: "US", base: "https://us.cloud.langfuse.com" },
  { value: "jp", label: "Japan", base: "https://jp.cloud.langfuse.com" },
  { value: "hipaa", label: "HIPAA", base: "https://hipaa.cloud.langfuse.com" },
  { value: "own", label: "Self-hosted", base: "" },
];

/** Whether a collector is Langfuse's, by its path. */
export function isLangfuse(endpoint: string): boolean {
  return endpoint.includes("/api/public/otel/");
}

/**
 * A Langfuse project as a collector: where an OTLP exporter posts its traces, Basic auth of the
 * public and the secret key, and the ingestion version that shows a trace at once instead of up
 * to ten minutes later.
 */
export function langfuseAs(host: string, publicKey: string, secretKey: string, pii: boolean): Wanted {
  return {
    endpoint: `${host.replace(/\/+$/, "")}/api/public/otel/v1/traces`,
    headers: { Authorization: `Basic ${btoa(`${publicKey}:${secretKey}`)}`, "x-langfuse-ingestion-version": "4" },
    pii,
  };
}
