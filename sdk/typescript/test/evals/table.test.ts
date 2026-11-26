/** Comparisons read as one benchmark, in each state a board of them is drawn in: nothing ended, nobody judged, one setup, several, several comparisons as one table, calls that do not count. */

import { describe, expect, it } from "vitest";

import type { Read, Row } from "../../src/evals/calls.js";
import { callersOf, endedOf, rowsOf, standingsOf, type Table } from "../../src/evals/table.js";

const BARS = { floor: 0.9, ceiling_s: 1.5 };
const FLASH = "thinks google/gemini-3.5-flash-lite";
const NO_LOG: Read = { not_counted: null, replies_s: [], unpriced: [], recording: null, timed: false, lines: [] };

let made = 0;
/** A call a caller completed under the flash model; `over` says what this one differs in. */
function row(over: Partial<Row> = {}): Row {
  made += 1;
  return {
    call: `call_${String(made)}`,
    persona: "books-a-visit",
    against: { llm: "google/gemini-3.5-flash-lite" },
    started_at: 100 + made,
    ended_at: 190 + made,
    end_reason: "caller_hung_up",
    score: { passed: true, reason: null },
    cost_usd: 0.05,
    latency: { e2e_latency: 1.2, llm_node_ttft: 0.5, tts_node_ttfb: 0.1, transcription_delay: null },
    why: null,
    goal: "held",
    judges: [{ name: "expected-outcome", verdict: "held", reason: "booked the visit" }],
    valid: true,
    invalid: null,
    ...over,
  };
}

const NOT_JUDGED: Partial<Row> = { score: null, goal: null, judges: [] };
const FAILED: Partial<Row> = { goal: "broken", score: { passed: false, reason: "moved it to Tuesday" }, judges: [{ name: "expected-outcome", verdict: "broken", reason: "moved it to Tuesday" }] };

const table = (rows: Row[], comparison: string = "cmp_1"): Table => ({ comparison, persona: "books-a-visit", personas: ["books-a-visit"], rows });
/** What a reader with no log says of a row: only what the gateway said of it. */
const read = (one: Row): Read => ({ ...NO_LOG, not_counted: one.valid === false ? (one.invalid ?? null) : null });

describe("comparisons read as one benchmark", () => {
  it("has no call and no setup while every call is still on the line", () => {
    const board = standingsOf([table([row({ ended_at: null, ...NOT_JUDGED })])], BARS, read);
    expect(board.calls).toEqual([]);
    expect(board.setups).toEqual([]);
    expect(board.verdict.passed).toBeNull();
  });

  it("gives no verdict when nobody judged a call, and still measures its reply", () => {
    const board = standingsOf([table([row(NOT_JUDGED)])], BARS, read);
    expect(board.verdict.passed).toBeNull();
    expect(board.setups).toHaveLength(1);
    expect(board.setups[0]?.completed).toMatchObject({ completed: 0, of: 0, share: null });
    expect(board.setups[0]?.clears).toEqual({ floor: null, ceiling: true });
    expect(board.setups[0]?.reply.p50).toBe(1.2);
  });

  it("holds one setup to both bars, with the failed call's reason on the call", () => {
    const board = standingsOf([table([row(), row(FAILED)])], BARS, read);
    expect(board.setups.map((setup) => setup.name)).toEqual([FLASH]);
    expect(board.setups[0]?.completed).toMatchObject({ completed: 1, of: 2, share: 0.5 });
    expect(board.setups[0]?.clears).toEqual({ floor: false, ceiling: true });
    expect(board.verdict).toMatchObject({ passed: false, cleared: [], winner: null });
    expect(board.calls.filter((call) => call.completed === false).map((call) => call.reason)).toEqual(["moved it to Tuesday"]);
  });

  it("keeps several setups apart, one that changes smart interruptions alone among them, and says which clear", () => {
    const slow = { e2e_latency: 2.1, llm_node_ttft: 0.9, tts_node_ttfb: 0.1, transcription_delay: null };
    const board = standingsOf([table([row(), row({ against: { llm: "openai/gpt-5.4-mini" }, latency: slow }), row({ against: { llm: "google/gemini-3.5-flash-lite", smart_interruptions: false } })])], BARS, read);
    expect(board.setups.map((setup) => setup.name)).toEqual([FLASH, `${FLASH} · smart interruptions off`, "thinks openai/gpt-5.4-mini"]);
    expect(board.setups.map((setup) => setup.clears.ceiling)).toEqual([true, true, false]);
    expect(board.verdict.passed).toBe(true);
    expect(board.verdict.cleared).toEqual([FLASH, `${FLASH} · smart interruptions off`]);
  });

  it("reads several comparisons as one table: the same caller rung again is the setup's next round", () => {
    const tables = [table([row()], "cmp_1"), table([row()], "cmp_2")];
    const board = standingsOf(tables, BARS, read);
    expect(board.calls.map((call) => [call.comparison, call.round])).toEqual([["cmp_1", 1], ["cmp_2", 2]]);
    expect(board.setups).toHaveLength(1);
    expect(board.setups[0]?.completed).toMatchObject({ completed: 2, of: 2 });
    expect(board.setups[0]?.rounds).toEqual([{ round: 1, completed: 1, of: 1 }, { round: 2, completed: 1, of: 1 }]);
    expect(board.verdict.passed).toBe(true);
  });

  it("leaves a call that does not count out of every number, and keeps it to be read with its reason", () => {
    const refused = { kind: "vendor" as const, why: "openai refused this call: insufficient_quota" };
    const board = standingsOf([table([row(), row({ valid: false, invalid: refused, ...NOT_JUDGED })])], BARS, read);
    expect(board.setups[0]).toMatchObject({ calls: 1, not_counted: 1, thin: false });
    expect(board.setups[0]?.completed).toMatchObject({ completed: 1, of: 1 });
    expect(board.calls.map((call) => [call.round, call.not_counted])).toEqual([[1, null], [0, refused]]);
    expect(board.verdict.passed).toBe(true);
  });

  it("holds a setup that lost most of its calls to no bar", () => {
    const lost = (kind: "vendor" | "platform"): Partial<Row> => ({ valid: false, invalid: { kind, why: "it broke" } });
    const board = standingsOf([table([row(), row(lost("vendor")), row(lost("platform"))])], BARS, read);
    expect(board.setups[0]).toMatchObject({ calls: 1, not_counted: 2, thin: true });
    expect(board.verdict).toMatchObject({ passed: false, cleared: [] });
    expect(board.verdict.says).toContain("lost most of its calls");
  });
});

describe("the rows of several comparisons", () => {
  it("are each call once, under the comparison that placed it first", () => {
    const one = row();
    const rows = rowsOf([table([one], "cmp_1"), table([one, row()], "cmp_2")]);
    expect(rows.map((each) => each.comparison)).toEqual(["cmp_1", "cmp_2"]);
  });

  it("count as ended when the call is over or never began", () => {
    const rows = endedOf([table([row(), row({ ended_at: null }), row({ ended_at: null, why: "no worker took it" })])]);
    expect(rows.map((each) => each.why)).toEqual([null, "no worker took it"]);
  });

  it("name their callers once, a comparison of one caller by its own", () => {
    const tables: Table[] = [{ comparison: "cmp_1", persona: "books-a-visit", personas: [], rows: [] }, { comparison: "cmp_2", persona: "books-a-visit", personas: ["books-a-visit", "cancels-late"], rows: [] }];
    expect(callersOf(tables)).toEqual(["books-a-visit", "cancels-late"]);
  });
});
