/** A comparison's printout: a call that ended in error never reads as held, and several runs are summed by configuration. */

import { describe, expect, it } from "vitest";

import type { ComparisonRow } from "../../../src/api/evals.js";
import { comparison, verdictOf } from "../../../src/evals/render/comparison.js";

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

// One call of a comparison as the gateway answers it once judged: who rang, on what, whether they got what they came for.
function ran(persona: string, llm: string, goal: "held" | "broken", cost: number, reply: number): ComparisonRow {
  return { ...A_ROW, persona, against: { llm }, end_reason: "caller_hung_up", goal, cost_usd: cost, latency: { ...A_ROW.latency, e2e_latency: reply } };
}

describe("several runs of a comparison, summed by configuration", () => {
  const rows = [
    ran("books", "acme/small", "held", 0.04, 1.2),
    ran("books", "acme/small", "held", 0.04, 1.4),
    ran("rushed", "acme/small", "broken", 0.04, 1.0),
    ran("rushed", "acme/small", "held", 0.04, 1.6),
    ran("books", "acme/big", "held", 0.06, 2.0),
    ran("books", "acme/big", "held", 0.06, 2.2),
    ran("rushed", "acme/big", "held", 0.06, 2.4),
    ran("rushed", "acme/big", "held", 0.06, 2.6),
  ];
  const table = { comparison: "cmp_1", agent: "dentist", persona: "books", personas: ["books", "rushed"], voice: true, repeats: 2, rows };
  const lines = comparison({ comparison: "cmp_1", refused: [], table });
  const of = (model: string): string => lines.filter((line) => line.includes(`thinks ${model}`)).at(-1) ?? "";

  it("counts each caller's runs that did its task, and all of them with their share", () => {
    expect(of("acme/small")).toContain("2 of 2");
    expect(of("acme/small")).toContain("1 of 2");
    expect(of("acme/small")).toContain("3 of 4 · 75%");
    expect(of("acme/big")).toContain("4 of 4 · 100%");
  });

  it("charges a completed call with the calls that failed beside it", () => {
    // Four calls at $0.04 with three done: $0.16 over 3, never the $0.04 one call cost.
    expect(of("acme/small")).toContain("$0.1600");
    expect(of("acme/small")).toContain("$0.0533");
    expect(of("acme/big")).toContain("$0.0600");
  });

  it("says the middle reply of a configuration's calls", () => {
    expect(of("acme/small")).toContain("1.30 s");
    expect(of("acme/big")).toContain("2.30 s");
  });

  it("puts the configuration that did the most first, and names each call's caller", () => {
    const summed = lines.slice(lines.findIndex((line) => line.startsWith("how often each did the callers' tasks")));
    expect(summed.findIndex((line) => line.includes("acme/big"))).toBeLessThan(summed.findIndex((line) => line.includes("acme/small")));
    expect(lines[0]).toContain("books, rushed against dentist · 8 calls");
    expect(lines.some((line) => line.includes("rushed") && line.includes("thinks acme/small") && line.includes("call_1"))).toBe(true);
  });

  it("says none completed where no run did the task, and divides by nothing", () => {
    const none = comparison({ comparison: "cmp_2", refused: [], table: { ...table, personas: ["books"], rows: [ran("books", "acme/small", "broken", 0.04, 1), ran("books", "acme/small", "broken", 0.04, 1)] } });
    expect(none.some((line) => line.includes("0 of 2 · 0%") && line.includes("none completed"))).toBe(true);
  });
});
