// The log column, folded from a REAL call: the one where somebody booked, tools and all.

import { reduce } from "../src/wire/reduce.js";
import { describe, expect, it } from "vitest";

import { brief, knownBy, rowsOf } from "../src/rows.js";
import { BOOKING } from "./a-real-booking.js";

const state = reduce(BOOKING);

describe("the log reads as the conversation", () => {
  it("folds into turns and tool runs", () => {
    expect(state.status).toBe("ended");
    expect(state.turns.length).toBeGreaterThanOrEqual(10);
    expect(state.tools.map((run) => run.name)).toEqual(["freeSlots", "propose", "who", "book"]);
  });

  it("draws a tool run above the reply it was called for, never after it", () => {
    const rows = rowsOf(state);
    const at = (name: string): number => rows.findIndex((row) => row.kind === "tool" && row.name === name);
    const said = (words: string): number => rows.findIndex((row) => row.kind === "turn" && row.text.includes(words));

    // The agent read the calendar BEFORE it said what was free. Drawn the other way round —
    // every turn, then every tool — the timeline is one that never happened.
    expect(at("freeSlots")).toBeLessThan(said("Thursday 24 September"));
    expect(at("book")).toBeLessThan(said("All set"));
    expect(said("Thursday would be great")).toBeLessThan(at("propose"));
  });

  it("gives every row what the column draws, and a tool row its raw values", () => {
    const rows = rowsOf(state);
    const book = rows.find((row) => row.kind === "tool" && row.name === "book");
    if (book?.kind !== "tool") throw new Error("no book row");
    expect(book.status).toBe("done");
    expect(book.output).toContain("14:00");
    const run = state.tools.find((one) => one.name === "book");
    expect(book.raw).toEqual({ arguments: run?.arguments, output: run?.output });

    const answered = rows.filter((row) => row.kind === "turn" && row.role === "agent" && row.ms !== undefined);
    expect(answered.length).toBeGreaterThan(0);
    for (const turn of answered) {
      if (turn.kind !== "turn") continue;
      expect(turn.ms).toBeGreaterThan(0);
      expect(turn.ms).toBeLessThan(60_000);
    }
  });

  it("knows the agent's own fields, and draws none of the empty ones", () => {
    const known = Object.fromEntries(knownBy(state));
    expect(known.stage).toBe("done");
    expect(known.day).toBe("2026-09-24");
    // An object is opened one level: a page shows the time, not a JSON blob.
    expect(known["meeting.time"]).toBe("14:00");
    expect(known["person.name"]).toBe("Ana Ruiz");
    expect(known).not.toHaveProperty("meeting");
    // `proposed` is cleared the moment the booking lands, so it is not a row.
    expect(known).not.toHaveProperty("proposed");
  });

  it("cuts a value too long for the column, never wraps it into the layout", () => {
    expect(brief("a".repeat(200), 10)).toBe(`${"a".repeat(9)}…`);
    expect(brief({ day: "Thursday" })).toBe('{"day":"Thursday"}');
    expect(brief(undefined)).toBe("");
  });
});
