/** The one way a date, an amount, a duration, a count or a size is written; the table a verb prints. */

import { describe, expect, it } from "vitest";

import { amount, bytes, clipped, count, date, duration, formatHint, formatNotice, formatPairs, money, timestamp } from "../../src/kit/format.js";
import { fields, table } from "../../src/kit/table.js";

describe("formats", () => {
  it("time, money, durations, counts and sizes as a terminal reads them", () => {
    expect(date(1_792_150_000)).toBe("2026-10-16 11:26");
    expect(date(null)).toBe("-");
    expect(timestamp("2026-10-16T08:26:40Z")).toBe("2026-10-16 08:26:40");
    expect([money(0.05), money(undefined)]).toEqual(["$0.0500", "-"]);
    expect([duration(0.84), duration(31.4), duration(84)]).toEqual(["0.8s", "31s", "1m 24s"]);
    expect([count(1, "call"), count(3, "call")]).toEqual(["1 call", "3 calls"]);
    expect([bytes(900), bytes(20_480), bytes(4 * 1024 * 1024)]).toEqual(["900 B", "20.0 kB", "4.0 MB"]);
    expect(clipped("abcdef", 4)).toBe("abc…");
  });

  it("a table pads every column but the last, headers uppercased; none for no rows", () => {
    expect(table(["id", "name"], [["a", "Ana"], ["long-id", null]])).toEqual(["ID       NAME", "a        Ana", "long-id  -"]);
    expect(table(["id"], [])).toEqual([]);
    expect(fields([["org", "clinica"], ["production", "yes"]])).toEqual(["org         clinica", "production  yes"]);
  });

  it("a next step is its own line at the foot, opened by an arrow, with no backticks", () => {
    expect(formatHint("pinecall agent set --help names them", "--all lists every one")).toBe("  → pinecall agent set --help names them · --all lists every one");
    expect(formatNotice("no base pushed yet: `pinecall docs push` sends one")).toEqual(["no base pushed yet", "  → pinecall docs push sends one"]);
    // A colon no command follows stays in the sentence: the step is after the first colon a command does.
    expect(formatNotice("--state: cannot read x.json — no such file")).toEqual(["--state: cannot read x.json — no such file"]);
    expect(formatNotice("nobody holds it (running: ana), so it rings nowhere: `pinecall line claim` takes it")).toEqual(["nobody holds it (running: ana), so it rings nowhere", "  → pinecall line claim takes it"]);
  });

  it("a record in words, never its JSON: nested fields by their path, lists by commas", () => {
    expect(formatPairs({ stage: "ask", message: { name: "Ana", about: "a delivery" } })).toBe("stage ask · message.name Ana · message.about a delivery");
    expect(formatPairs({ judges: ["disclosed", "promises"] })).toBe("judges disclosed, promises");
    expect(formatPairs({ done: null })).toBe("done —");
    expect([amount(3483), amount(0.75)]).toEqual(["3,483", "0.8"]);
  });
});
