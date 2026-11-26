/** A benchmark at a terminal: with several conditions, a table of each setup under each line. */

import { describe, expect, it } from "vitest";

import { benchmark, shiftOf } from "../../../src/evals/render/benchmark.js";
import type { Benchmark } from "../../../src/evals/service/benchmark.js";
import { underEach, type Condition } from "../../../src/evals/service/conditions.js";
import { verdictOf, type BenchCall } from "../../../src/evals/service/scorecard.js";

const BARS = { floor: 0.9, ceiling_s: 1.5 };
const CLEAN: Condition = { name: "clean", line: {}, comparisons: ["cmp_1"] };
const A_TELEVISION: Condition = { name: "television-20", line: { ambience: "television", "background-noise": 20 }, comparisons: ["cmp_2"] };
const hearing = (phantom: number): BenchCall["hearing"] => ({ lines: 6, unanswered: 0, phantom_turns: phantom, cut_by_the_room: 0, cut_by_a_murmur: 0, talked_over: 0, word_error_rate: 0.03 });

const A_CALL: BenchCall = {
  call: "call_1",
  comparison: "cmp_1",
  caller: "books-a-visit",
  setup: "thinks a/model",
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
  hearing: hearing(0),
  recording: null,
  timed: false,
  lines: [],
};

describe("a number a condition moved", () => {
  it("is said as what it is under the condition", () => {
    expect(shiftOf({ what: "turns nobody said a call", was: 0, now: 15.5 })).toBe("16 turns nobody said a call");
    expect(shiftOf({ what: "seconds to reply", was: 0.7, now: 7.92 })).toBe("7.9 seconds to reply");
    expect(shiftOf({ what: "word error", was: 0.03, now: 0.4 })).toBe("40% word error");
    expect(shiftOf({ what: "word error", was: 0.03, now: 18.9 })).toBe("more words heard than said");
  });
});

describe("a benchmark of several conditions at a terminal", () => {
  const calls = [A_CALL, { ...A_CALL, call: "call_2", condition: "television-20", completed: false, hearing: hearing(15) }];
  const each = underEach({ llm: "a/model" }, calls, [CLEAN, A_TELEVISION], ["books-a-visit"], BARS);
  const setups = [{ ...each.baseline, under: each.under }];
  const report = {
    agent: "front-desk",
    bars: BARS,
    setups,
    verdict: verdictOf(setups, BARS),
    conditions: [
      { name: "clean", line: {}, says: "the line as the callers have it", comparisons: ["cmp_1"], calls: 1, counted: 1 },
      { name: "television-20", line: A_TELEVISION.line, says: "television 20 dB under the caller", comparisons: ["cmp_2"], calls: 1, counted: 1 },
    ],
    calls,
    on_the_line: 0,
  } as unknown as Benchmark;

  it("prints each setup under each line: what it completed there, whether it clears both bars, and what the line moved most", () => {
    const lines = benchmark({ report, folder: null });
    const head = lines.findIndex((line) => line.startsWith("THE AGENT RUNS ON") && line.includes("TELEVISION-20"));
    expect(head).toBeGreaterThan(0);
    expect(lines[head + 1]).toContain("1/1 ✓");
    expect(lines[head + 1]).toContain("0/1 ✗ · 15 turns nobody said a call");
    expect(lines.some((line) => line.includes("television-20: television 20 dB under the caller"))).toBe(true);
  });

  it("prints no such table for a benchmark of one line", () => {
    const lines = benchmark({ report: { ...report, conditions: [] }, folder: null });
    expect(lines.filter((line) => line.startsWith("THE AGENT RUNS ON"))).toHaveLength(1);
  });
});
