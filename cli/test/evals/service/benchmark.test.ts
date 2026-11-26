/** A benchmark's gate: the baseline's line as before, and a condition a setup must hold under too. */

import { describe, expect, it } from "vitest";

import { requireCleared } from "../../../src/evals/service/benchmark.js";
import { heldUnderEvery, underEach, type Condition } from "../../../src/evals/service/conditions.js";
import { verdictOf, type BenchCall, type Benchmark, type Setup } from "@pinecall/agents/evals";

const BARS = { floor: 0.9, ceiling_s: 1.5 };
const CLEAN: Condition = { name: "clean", line: {}, comparisons: ["cmp_1"] };
const A_TELEVISION: Condition = { name: "television-20", line: { ambience: "television", "background-noise": 20 }, comparisons: ["cmp_2"] };

const A_CALL: BenchCall = {
  call: "call_1",
  comparison: "cmp_1",
  caller: "books-a-visit",
  setup: "",
  condition: "clean",
  round: 1,
  not_counted: null,
  completed: true,
  reason: null,
  ended: "caller_hung_up",
  started_at: 100,
  length_s: 95,
  reply_s: 1.2,
  replies_s: [1.2],
  slowest_reply_s: 1.2,
  cost_usd: 0.05,
  unpriced: [],
  stages: { llm_ttft: null, tts_ttfb: null, transcription_delay: null, end_of_turn_delay: null },
  judges: [],
  hearing: null,
  recording: null,
  timed: false,
  lines: [],
};

// A setup with one call on a clean line and one under the television: completed there, or not.
function setup(model: string, underTheTelevision: boolean): Setup {
  const each = underEach({ llm: model }, [A_CALL, { ...A_CALL, call: "call_2", condition: "television-20", completed: underTheTelevision }], [CLEAN, A_TELEVISION], ["books-a-visit"], BARS);
  return { ...each.baseline, under: each.under };
}

function made(setups: Setup[]): { report: Benchmark; folder: null } {
  const verdict = verdictOf(setups, BARS);
  verdict.held_under_every = heldUnderEvery(setups, [CLEAN, A_TELEVISION]).names;
  return { report: { setups, verdict } as unknown as Benchmark, folder: null };
}

describe("a benchmark's gate", () => {
  it("passes on the baseline's line whatever a condition did, unless the condition is named", () => {
    const report = made([setup("a/falls", false)]);
    expect(() => requireCleared(report, { gate: true, gateUnder: [] })).not.toThrow();
    expect(() => requireCleared(report, { gate: false, gateUnder: [] })).not.toThrow();
    expect(() => requireCleared(report, { gate: false, gateUnder: ["television-20"] })).toThrow("the benchmark failed under television-20");
  });

  it("held under a condition is one setup clearing both bars there and on the baseline's line", () => {
    expect(() => requireCleared(made([setup("a/falls", false), setup("a/holds", true)]), { gate: true, gateUnder: ["television-20"] })).not.toThrow();
  });
});
