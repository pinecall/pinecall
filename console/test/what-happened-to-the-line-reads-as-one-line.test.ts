/** A transfer, a hold and an ask for a person are sentences in the log, never folded rows. */

import { describe, expect, it } from "vitest";

import { wantsAPerson } from "@pinecall/core/calls";
import { lineMark } from "../src/lib/line-mark.js";
import { rowsOf } from "../src/screens/call/timeline-rows.js";

const entry = (seq: number, type: string, data: Record<string, unknown>) =>
  ({ seq, type, ts: seq, call: "call_1", agent: "sofia", ephemeral: false, data }) as never;

const line = (attention: unknown) => ({ call: "call_1", status: "active", live: true, attention }) as never;

describe("what happened to the line", () => {
  it("says who the caller was sent to, and says when nobody moved", () => {
    expect(lineMark(entry(4, "call.transferred", { to: "+34910000099", mode: "warm", ok: true }))).toEqual({
      said: "transferred to +34910000099",
      note: "warm",
    });
    expect(lineMark(entry(4, "call.transferred", { to: "+34910000099", mode: null, ok: false, error: "no line" }))).toEqual({
      said: "the transfer to +34910000099 did not take",
      note: "no line",
    });
  });

  it("says what a person was asked for, and whether one came", () => {
    expect(lineMark(entry(5, "attention.requested", { reason: "wants a refund", wait_s: 60 }))).toEqual({
      said: "the agent asked for a person: wants a refund",
      note: "waits 60s",
    });
    expect(lineMark(entry(6, "attention.answered", { ok: true, by: { id: "sup_1", name: "Lucía" } }))).toEqual({
      said: "a person took the line",
      note: "Lucía",
    });
    expect(lineMark(entry(6, "attention.answered", { ok: false, by: null, error: "nobody took the line within 60s" }))).toEqual({
      said: "nobody took the line",
      note: "nobody took the line within 60s",
    });
  });

  it("is a row of the transcript and not one of the folded ones", () => {
    const state = { turns: [], tools: [], confirms: [] } as never;
    const rows = rowsOf([entry(5, "attention.requested", { reason: "wants a refund", wait_s: 60 }), entry(7, "agent.state", { state: "listening" })], state);
    expect(rows.map((row) => row.kind)).toEqual(["line", "quiet"]);
  });

  it("is a caller waiting only while nobody has taken the line", () => {
    expect(wantsAPerson(line({ status: "open", reason: "r", wait_s: 60, asked_at: 1, by: null }))).toBe(true);
    expect(wantsAPerson(line({ status: "answered", reason: "r", wait_s: 60, asked_at: 1, by: null }))).toBe(false);
    expect(wantsAPerson(line(null))).toBe(false);
  });
});
