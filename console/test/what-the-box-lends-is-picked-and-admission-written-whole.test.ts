/** The lends picker's value is the wire's — null, [] or the entries — and admission is written one world at a time. */

import { describe, expect, test } from "vitest";

import { lendsOf, modeOf } from "../src/screens/box/lends";
import { typedOf, withWorld } from "../src/screens/box/settings-admission";

describe("what the box lends, as picked", () => {
  test("null lends every key, an empty list none, a list the entries named", () => {
    expect(modeOf(null)).toBe("all");
    expect(modeOf(undefined)).toBe("all");
    expect(modeOf([])).toBe("none");
    expect(modeOf(["google"])).toBe("some");
  });

  test("the value written is null, empty, or the entries trimmed, deduplicated and sorted", () => {
    expect(lendsOf("all", ["google"])).toBeNull();
    expect(lendsOf("none", ["google"])).toEqual([]);
    expect(lendsOf("some", [" google", "cartesia", "google", "", "anthropic/claude-haiku-5-5"])).toEqual([
      "anthropic/claude-haiku-5-5",
      "cartesia",
      "google",
    ]);
  });
});

describe("admission, one world at a time", () => {
  const ROW = { first: { production: { minutes: 0, lends: [] } }, later: null };

  test("a world's fields read as typed: a number, or empty for no limit", () => {
    const typed = typedOf({ minutes: 30, evals: 100, lends: ["google"] });
    expect(typed["minutes"]).toBe("30");
    expect(typed["evals"]).toBe("100");
    expect(typed["messages"]).toBe("");
  });

  test("writing the sandbox keeps production as it was, and an empty field is no limit", () => {
    const written = withWorld(ROW, "first", "sandbox", { minutes: "30", messages: "" }, ["google"]);
    expect(written.first["sandbox"]).toEqual({ minutes: 30, lends: ["google"] });
    expect(written.first["production"]).toEqual({ minutes: 0, lends: [] });
    expect(written.later).toBeNull();
  });

  test("a person's later orgs are their own side of the row", () => {
    const written = withWorld(ROW, "later", "sandbox", { minutes: "0" }, []);
    expect(written.later).toEqual({ sandbox: { minutes: 0, lends: [] } });
    expect(written.first).toEqual(ROW.first);
  });
});
