/** Knowledge as a terminal reads it: the memory policy of an agent whose class sets it. */

import { describe, expect, it } from "vitest";

import { policy } from "../../src/knowledge/render.js";

const answer = (fixed: string[]): never => ({ world: "sandbox", yours: null, team: null, production: null, fixed }) as never;

describe("policy", () => {
  it("says the class sets it, where three corners with nothing set would read as an agent that remembers nothing", () => {
    expect(policy({ agent: "front-desk", answer: answer(["llm", "memory"]) })).toEqual([
      "front-desk · sandbox",
      "  set by the class: no setting is read for it",
      "  → agents/front-desk/ holds the class: its memory field says what is kept and what never is",
    ]);
  });

  it("prints each corner where the policy is a setting", () => {
    expect(policy({ agent: "front-desk", answer: answer(["llm"]) })).toEqual([
      "front-desk · sandbox",
      "  yours       (team's)",
      "  team        nothing set",
      "  production  nothing set",
    ]);
  });
});
