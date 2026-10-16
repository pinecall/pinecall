/** Entries the runtime writes since 0.1.3 parse: the worker on call.started, the judges on call.score, a simulation or a run on call.summary, a judge tried, and the events since. */

import { expect, it } from "vitest";

import { decodeEntry, eventOf } from "../../src/wire/codec.js";

// As cloud.pinecall.io writes them (2026-10-01). An app on 0.9.12 dropped call.started for its
// `worker`, so it never held the call and every tool answered "no longer being served".
const entry = (type: string, data: Record<string, unknown>): unknown => ({
  seq: 2, ts: 1790878264.33, call: "call_1ee0", agent: "pinecall", type, ephemeral: false, data,
});

it("reads call.started with the worker that runs the call", () => {
  const started = { channel: "web", direction: "inbound", from: "web_7fb3", to: "pinecall", caller: null, started_at: 1790878264.3, env: "production", worker: "pinecall-runtime-a" };
  expect(eventOf(decodeEntry(entry("call.started", started)))).toMatchObject({ data: { worker: "pinecall-runtime-a" } });
  const attached = { app: "app_1", started, state: {}, seq: 9 };
  expect(eventOf(decodeEntry(entry("call.attached", attached)))).toMatchObject({ data: { started: { worker: "pinecall-runtime-a" } } });
});

it("reads call.score with the judge that gave it", () => {
  const score = { passed: true, judges: [], judge_calls: 1, judge_cost_usd: 0.002, judged_by: { provider: "anthropic", model: "claude-haiku-5-5", criteria: "c3f1" } };
  expect(eventOf(decodeEntry(entry("call.score", score)))).toMatchObject({ data: { judged_by: { model: "claude-haiku-5-5" } } });
});

it("reads call.score whose judges did not apply, classified, or ran on the org's own key", () => {
  const evidence = { seqs: [4] };
  const judges = [
    { name: "consent", verdict: "na", criteria: "q", reason: "no irreversible tool ran", evidence: { seqs: [] } },
    { name: "sentiment", verdict: "classified", criteria: "q", reason: "calm", evidence, choice: "positive" },
    { name: "relevance", verdict: "classified", criteria: "q", reason: "on topic", evidence, score: 4 },
  ];
  const score = { judges, judge_calls: 3, evals: 2, own_key: true };
  expect(eventOf(decodeEntry(entry("call.score", score)))).toMatchObject({
    data: { evals: 2, own_key: true, judges: [{ verdict: "na" }, { choice: "positive" }, { score: 4 }] },
  });
});

it("reads call.summary of a call a simulated caller played", () => {
  const summary = { reason: "agent_hung_up", outcome: "booked", duration_s: 40, turns: 6, usage: [], cost: { usd: 0.01, rows: [], unpriced: [] }, simulated: true };
  expect(eventOf(decodeEntry(entry("call.summary", summary)))).toMatchObject({ data: { simulated: true } });
});

it("reads a written golden's call.summary with its run, evals.spent, and credits.exhausted for evals", () => {
  const summary = { reason: "agent_hung_up", outcome: "booked", duration_s: 40, turns: 6, usage: [], cost: { usd: 0.01, rows: [], unpriced: [] }, run: "run_8f4a2c" };
  expect(eventOf(decodeEntry(entry("call.summary", summary)))).toMatchObject({ data: { run: "run_8f4a2c" } });
  const tried = { kind: "try", name: "grounded", env: "sandbox", calls: ["call_1", "call_2"], evals: 2, judge_calls: 2, judge_cost_usd: 0.002 };
  expect(eventOf(decodeEntry(entry("evals.spent", tried)))).toMatchObject({ data: { evals: 2, env: "sandbox" } });
  const refused = { org: "org_1", quota: "evals", used: 500, limit: 500 };
  expect(eventOf(decodeEntry(entry("credits.exhausted", refused)))).toMatchObject({ data: { quota: "evals" } });
});

it("reads call.started with what a simulated caller expects", () => {
  const started = { channel: "web", direction: "inbound", from: "simulated_caller", to: "pinecall", caller: null, started_at: 1790878264.3, persona: "in-a-hurry", expects: ["The agent should get to the point."] };
  expect(eventOf(decodeEntry(entry("call.started", started)))).toMatchObject({ data: { expects: ["The agent should get to the point."] } });
});

it("reads spend.unusual and vendor.switched", () => {
  const spend = { org: "org_1", day: "2026-10-01", today_usd: 31.5, usual_usd: 9.2, multiple: 3.4 };
  expect(eventOf(decodeEntry(entry("spend.unusual", spend))).type).toBe("spend.unusual");
  const switched = { stage: "tts", vendor: "cartesia", model: "sonic-3", available: false, serving: "elevenlabs", serving_model: "eleven_flash_v2_5" };
  expect(eventOf(decodeEntry(entry("vendor.switched", switched))).type).toBe("vendor.switched");
});
