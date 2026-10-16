/** The Monitors screen reads the runtime's rows field for field, adds one with the rule in the body, and drops one by id. */

import { expect, test } from "vitest";
import { z } from "zod";

import { addMonitor, dropMonitor, readMonitors } from "../src/screens/monitors/door";
import { ruleOf, valueOf } from "../src/screens/monitors/metrics";

const CREDENTIALS = { base: "/", key: "pk_test" };
// runtime wire/rest/monitors.py: MonitorRow.
const SLOW = { id: "mon_3f9a1c2b4d5e", name: "slow answers", metric: "e2e_median_s", above: true, threshold: 2, window_days: 7, agent: null, created_by: "m_ana", fired_on: "2026-10-08", fired_value: 2.41 };

let asked: { url: string; method: string; body: unknown }[] = [];

function answering(body: unknown, status = 200): void {
  asked = [];
  globalThis.window = { location: { origin: "https://cloud.pinecall.io" } } as unknown as Window & typeof globalThis;
  globalThis.fetch = (async (url: URL, init?: RequestInit) => {
    asked.push({ url: url.toString(), method: init?.method ?? "GET", body: init?.body === undefined ? undefined : JSON.parse(String(init.body)) });
    return new Response(status === 204 ? null : JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
  }) as typeof fetch;
}

test("the monitors are the runtime's rows, and a renamed field is refused", async () => {
  answering({ monitors: [SLOW] });
  expect(await readMonitors(CREDENTIALS)).toEqual([SLOW]);
  answering({ monitors: [{ ...SLOW, fired_on: undefined }] });
  await expect(readMonitors(CREDENTIALS)).rejects.toBeInstanceOf(z.ZodError);
});

test("adding one posts the rule and whose agent; dropping one is a DELETE by id", async () => {
  answering({ ...SLOW, fired_on: null, fired_value: null }, 201);
  const kept = await addMonitor(CREDENTIALS, { name: "slow answers", metric: "e2e_median_s", above: true, threshold: 2, window_days: 7, agent: null });
  expect(kept.id).toBe(SLOW.id);
  expect(asked[0]).toEqual({ url: "https://cloud.pinecall.io/v1/monitors", method: "POST", body: { name: "slow answers", metric: "e2e_median_s", above: true, threshold: 2, window_days: 7, agent: null } });
  answering(null, 204);
  await dropMonitor(CREDENTIALS, SLOW.id);
  expect(asked[0]).toMatchObject({ url: `https://cloud.pinecall.io/v1/monitors/${SLOW.id}`, method: "DELETE" });
});

test("a rule and a value are said in the metric's unit", () => {
  expect(ruleOf(SLOW)).toBe("End-to-end latency, median above 2.00 s over 7 days");
  expect(ruleOf({ metric: "held_rate", above: false, threshold: 0.9, window_days: 1 })).toBe("Held rate below 90% over 1 day");
  expect(valueOf("spend_usd", 21.5)).toBe("$21.50");
  expect(valueOf("made_up", 3)).toBe("3");
});
