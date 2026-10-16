// A written call measures no end-to-end latency — nobody spoke — so a reply carries the model's ttft instead.

import { initialState } from "../src/wire/reduce.js";
import { describe, expect, it } from "vitest";

import { rowsOf } from "../src/rows.js";

describe("a written reply has a time to first token", () => {
  it("carries ttft when the wire measured no e2e latency", () => {
    const state = initialState();
    state.turns.push(
      { role: "user", speech_id: "sp_1", text: "Thursday", metrics: {} },
      { role: "agent", speech_id: "sp_2", text: "Two or four?", interrupted: false, metrics: { llm_node_ttft: 0.5266 } },
    );
    const [asked, answered] = rowsOf(state);
    expect(asked).toMatchObject({ kind: "turn", role: "user", ms: undefined, ttft: undefined });
    expect(answered).toMatchObject({ kind: "turn", role: "agent", ms: undefined, ttft: 527 });
  });

  it("carries both when a spoken call measured both", () => {
    const state = initialState();
    state.turns.push({
      role: "agent", speech_id: "sp_2", text: "Two or four?", interrupted: false,
      metrics: { e2e_latency: 0.74, llm_node_ttft: 0.31 },
    });
    expect(rowsOf(state)[0]).toMatchObject({ ms: 740, ttft: 310 });
  });
});
