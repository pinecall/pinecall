/** An org with no agent opens on the guide once its agents are known; one that has an agent, or is still loading, does not. */

import { describe, expect, it } from "vitest";

import { isFirstRun } from "../src/screens/welcome/first-run";

describe("the welcome guide is due", () => {
  it("for an org that holds no agent", () => {
    expect(isFirstRun(true, 0)).toBe(true);
  });
  it("not while the agents are still being read", () => {
    expect(isFirstRun(false, 0)).toBe(false);
  });
  it("not once an agent is held", () => {
    expect(isFirstRun(true, 1)).toBe(false);
  });
});
