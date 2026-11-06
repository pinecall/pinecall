/** A comparison's judges column: a call that ended in error never reads as held. */

import { describe, expect, it } from "vitest";

import type { ComparisonRow } from "../../../src/api/evals.js";
import { verdictOf } from "../../../src/evals/render/index.js";

const A_ROW: ComparisonRow = {
  call: "call_1",
  persona: "booking-ar",
  against: { stt: "deepgram" },
  started_at: 100,
  ended_at: 117,
  turns: 0,
  end_reason: "error",
  score: { held: 1, judged: 1, passed: true, reason: null },
  cost_usd: 0.0042,
  latency: { e2e_latency: null, llm_node_ttft: null, tts_node_ttfb: null, transcription_delay: null, end_of_turn_delay: null },
  why: null,
};

describe("the judges column of a comparison", () => {
  it("says a call ended in error even when a judge held on what little it had", () => {
    expect(verdictOf(A_ROW)).toBe("ended in error");
  });

  it("gives the judges' count of a call that ended as calls do", () => {
    expect(verdictOf({ ...A_ROW, turns: 6, end_reason: "agent_hung_up" })).toBe("✓ 1/1");
  });
});
