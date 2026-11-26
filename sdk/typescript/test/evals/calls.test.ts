/** A comparison's row as a benchmark's call: whether its caller got what it came for, whose reason it carries, and the round it is. */

import { describe, expect, it } from "vitest";

import { callOf, completedOf, numberRounds, type Read, type Row } from "../../src/evals/calls.js";

const A_ROW: Row = {
  call: "call_1",
  persona: "books-a-visit",
  against: { llm: "google/gemini-3.5-flash-lite" },
  started_at: 100,
  ended_at: 190,
  end_reason: "caller_hung_up",
  score: { passed: false, reason: "was curt" },
  cost_usd: 0.05,
  latency: { e2e_latency: 1.2, llm_node_ttft: 0.5, tts_node_ttfb: 0.1, transcription_delay: null },
  why: null,
};
const NO_LOG: Read = { not_counted: null, replies_s: [], unpriced: [], recording: null, timed: false, lines: [] };
const THE_GOAL = { name: "expected-outcome", verdict: "held", reason: "booked the visit" };

describe("whether a caller got what it came for", () => {
  it("is its goal's judge when it expected something, whatever the other judges said", () => {
    expect(completedOf({ ...A_ROW, goal: "held" })).toBe(true);
    expect(completedOf({ ...A_ROW, goal: "broken", score: { passed: true, reason: null } })).toBe(false);
  });

  it("is every judge when it expected nothing, and nobody's when nobody judged", () => {
    expect(completedOf({ ...A_ROW, goal: null })).toBe(false);
    expect(completedOf({ ...A_ROW, goal: null, score: null })).toBeNull();
  });
});

describe("a row as a benchmark's call", () => {
  it("is named by the values it ran on and carries the goal's reason before any other", () => {
    const call = callOf({ ...A_ROW, comparison: "cmp_1", goal: "held", judges: [THE_GOAL] }, { ...NO_LOG, replies_s: [1.1, 1.3] });
    expect(call).toMatchObject({ setup: "thinks google/gemini-3.5-flash-lite", caller: "books-a-visit", comparison: "cmp_1", completed: true, reason: "booked the visit", length_s: 90, reply_s: 1.2, replies_s: [1.1, 1.3], round: 0 });
    expect("condition" in call).toBe(false);
  });

  it("says its condition when it was placed under one, and has no length while it never ended", () => {
    const call = callOf({ ...A_ROW, comparison: "cmp_1", condition: "street-10", ended_at: null }, NO_LOG);
    expect(call).toMatchObject({ condition: "street-10", length_s: null, reason: "was curt" });
  });
});

describe("the round a call is", () => {
  it("is the caller's nth under its setup in the order they started, a call that does not count taking none", () => {
    const under = (call: string, started_at: number, over: Partial<Row> = {}, read: Read = NO_LOG): ReturnType<typeof callOf> => callOf({ ...A_ROW, call, started_at, comparison: "cmp_1", ...over }, read);
    const calls = [
      under("third", 300),
      under("first", 100),
      under("lost", 200, {}, { ...NO_LOG, not_counted: { kind: "platform", why: "the call ended in error" } }),
      under("other-caller", 150, { persona: "cancels-late" }),
      under("other-setup", 160, { against: { llm: "openai/gpt-5.4-mini" } }),
    ];
    numberRounds(calls);
    expect(Object.fromEntries(calls.map((call) => [call.call, call.round]))).toEqual({ first: 1, lost: 0, third: 2, "other-caller": 1, "other-setup": 1 });
  });
});
