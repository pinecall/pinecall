/** The one way a date, an amount, a duration, a count or a size is written; the table a verb prints. */

import { describe, expect, it } from "vitest";

import { bytes, clipped, count, date, duration, money, timestamp } from "../../src/kit/format.js";
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
});
