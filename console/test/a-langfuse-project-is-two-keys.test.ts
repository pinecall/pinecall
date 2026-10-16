/** Langfuse as a collector: the region's OTLP traces URL, and the Basic auth and ingestion headers its two keys make. */

import { expect, test } from "vitest";

import { isLangfuse, langfuseHeaders, langfuseTraces } from "../src/screens/telemetry/langfuse";

test("a Langfuse host is its OTLP traces path, a trailing slash or not", () => {
  expect(langfuseTraces("https://cloud.langfuse.com")).toBe("https://cloud.langfuse.com/api/public/otel/v1/traces");
  expect(langfuseTraces("https://langfuse.example.com/")).toBe("https://langfuse.example.com/api/public/otel/v1/traces");
  expect(isLangfuse(langfuseTraces("https://us.cloud.langfuse.com"))).toBe(true);
  expect(isLangfuse("https://otlp.datadoghq.eu/v1/traces")).toBe(false);
});

test("the two keys are Basic auth, and the ingestion version shows a trace at once", () => {
  expect(langfuseHeaders("pk-lf-1", "sk-lf-2")).toEqual({ Authorization: `Basic ${btoa("pk-lf-1:sk-lf-2")}`, "x-langfuse-ingestion-version": "4" });
});
