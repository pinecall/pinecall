/** Whose keys a call runs on, from GET /v1/limits's lends and the vendors the org brought; and the limits card's meters. */

import { describe, expect, test } from "vitest";

import { keysSaid, lending } from "../src/lib/limits";
import { startsAgain, usedOf } from "../src/screens/overview/limits-card";

describe("what the box lends of a vendor", () => {
  test("lends null lends every vendor the box holds a key for", () => {
    expect(lending(null, "cartesia")).toBe("all");
  });

  test("a vendor named lends all its models, a vendor/model entry only some, and the rest nothing", () => {
    const lends = ["google", "anthropic/claude-haiku-5-5"];
    expect(lending(lends, "google")).toBe("all");
    expect(lending(lends, "anthropic")).toBe("some");
    expect(lending(lends, "openai")).toBe("none");
  });

  test("an empty list lends nothing", () => {
    expect(lending([], "google")).toBe("none");
  });
});

describe("the keys line", () => {
  test("names the org's own keys first, then what the box lends", () => {
    expect(keysSaid(["openai", "anthropic"], ["google"])).toBe("Yours: anthropic, openai · lent by the box: google");
  });

  test("says a box that lends everything and a box that lends nothing in words", () => {
    expect(keysSaid([], null)).toBe("Yours: none · lent by the box: every vendor it holds a key for");
    expect(keysSaid([], [])).toContain("bring a key for every vendor");
  });
});

describe("the limits card", () => {
  test("a meter is what is used of the limit, or no limit", () => {
    expect(usedOf({ limit: 30, used: 12.44 })).toEqual({ value: "12.4", of: "of 30" });
    expect(usedOf({ limit: null, used: 3 })).toEqual({ value: "3", of: "no limit" });
  });

  test("the monthly ones start again on the first of next month, January after December", () => {
    expect(startsAgain(new Date(Date.UTC(2026, 9, 13)))).toBe("1 Nov");
    expect(startsAgain(new Date(Date.UTC(2026, 11, 31)))).toBe("1 Jan");
  });
});
