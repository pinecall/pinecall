/** Agent turns are placed when speech started, not when the log entry was written. */

import { describe, expect, it } from "vitest";

import { rowsOf } from "../src/screens/call/timeline-rows.js";

// A turn is logged when the sentence ends, but a tool runs mid-sentence, so arrival order puts the
// tool first. Order turns by their `agent.state → speaking` entry instead.
const entry = (seq: number, type: string, data: Record<string, unknown>) =>
  ({ seq, type, ts: seq, call: "call_1", agent: "sofia", ephemeral: false, data });

describe("a tool that ran while the agent was still talking", () => {
  it("is drawn after the line that announced it, not before", () => {
    const state = {
      turns: [{ role: "agent", speech_id: "sp_1", item_id: "i_1", text: "Checking that now.", interrupted: false, metrics: {} }],
      tools: [{ call_id: "c_1", name: "setServiceAddress" }],
      confirms: [],
    } as never;

    const rows = rowsOf(
      [
        entry(31, "agent.state", { state: "speaking" }),
        entry(37, "tool.call", { call_id: "c_1", name: "setServiceAddress", arguments: {} }),
        entry(63, "turn.agent", { speech_id: "sp_1", item_id: "i_1", text: "Checking that now.", interrupted: false, metrics: {} }),
      ] as never,
      state,
    );

    expect(rows.filter((row) => row.kind !== "quiet").map((row) => row.kind)).toEqual(["turn", "tool"]);
  });
});
