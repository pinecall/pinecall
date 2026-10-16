/** The Telemetry screen reads the collector by header name, sets it with the headers in the body, and takes null for none. */

import { expect, test } from "vitest";
import { z } from "zod";

import { dropCollector, putCollector, readCollector, traceIdOf } from "../src/lib/telemetry";

const CREDENTIALS = { base: "/", key: "pk_test" };
// runtime wire/rest/telemetry.py: TelemetryResponse.
const A_COLLECTOR = { endpoint: "https://otel.example.test/v1/traces", header_names: ["x-api-key"], pii: false };

let asked: { url: string; method: string; body: unknown }[] = [];

function answering(body: unknown): void {
  asked = [];
  globalThis.window = { location: { origin: "https://cloud.pinecall.io" } } as unknown as Window & typeof globalThis;
  globalThis.fetch = (async (url: URL, init?: RequestInit) => {
    asked.push({ url: url.toString(), method: init?.method ?? "GET", body: init?.body === undefined ? undefined : JSON.parse(String(init.body)) });
    return new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } });
  }) as typeof fetch;
}

test("the collector is read by header name, null when the org sends its traces nowhere, and a renamed field is refused", async () => {
  answering(A_COLLECTOR);
  expect(await readCollector(CREDENTIALS)).toEqual(A_COLLECTOR);
  answering(null);
  expect(await readCollector(CREDENTIALS)).toBeNull();
  answering({ ...A_COLLECTOR, header_names: undefined });
  await expect(readCollector(CREDENTIALS)).rejects.toBeInstanceOf(z.ZodError);
});

test("a trace id is the call id's hex, and a carrier's call id hashes to one", async () => {
  expect(await traceIdOf("call_7216eb82996a429f88ddd4173cff5c3f")).toBe("7216eb82996a429f88ddd4173cff5c3f");
  const hashed = await traceIdOf("call-_+34607827824_GCrodJQ2ozT9");
  expect(hashed).toMatch(/^[0-9a-f]{32}$/);
  expect(hashed).not.toBe(await traceIdOf("call-_+34600000000_x"));
});

test("setting it sends the endpoint, the headers and pii in the body, and dropping it is a DELETE", async () => {
  answering(null);
  await putCollector(CREDENTIALS, A_COLLECTOR.endpoint, { "x-api-key": "made-up" }, true);
  expect(asked[0]).toEqual({ url: "https://cloud.pinecall.io/v1/telemetry", method: "PUT", body: { endpoint: A_COLLECTOR.endpoint, headers: { "x-api-key": "made-up" }, pii: true } });
  answering(null);
  await dropCollector(CREDENTIALS);
  expect(asked[0]?.method).toBe("DELETE");
});
