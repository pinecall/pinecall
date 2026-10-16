/** A simulation's edges: the persona in the gateway's shape, and the exit a score makes. */

import { describe, expect, it } from "vitest";

import { callerOf, exitCodeOf, SimulateInput, type Simulated } from "../../../src/evals/service/simulation.js";
import { A_PERSONA } from "../../support/fixtures.js";

const SIMULATED: Simulated = { persona: "apurado", goal: "book", call: "call_1", agentTurns: 4, callerTurns: 4, line: null, medians: {}, score: null, unjudged: false };

describe("the caller", () => {
  it("leaves out what the persona did not set", () => {
    expect(callerOf({ ...A_PERSONA, facts: {} })).toEqual({ name: "apurado", goal: A_PERSONA.goal, style: A_PERSONA.style, behavior: A_PERSONA.behavior });
  });

  it("carries what it did", () => {
    expect(callerOf({ ...A_PERSONA, llm: "openai/gpt-5.4-mini", voice: "cartesia-luis", expects: ["is offered a slot"] })).toMatchObject({
      facts: { name: "Luis" },
      llm: "openai/gpt-5.4-mini",
      voice: "cartesia-luis",
      expects: ["is offered a slot"],
    });
  });
});

describe("the exit", () => {
  it("is 1 only when a judge answered broken", () => {
    expect(exitCodeOf(SIMULATED)).toBe(0);
    expect(exitCodeOf({ ...SIMULATED, score: { passed: true, judges: [] } as never })).toBe(0);
    expect(exitCodeOf({ ...SIMULATED, score: { passed: false, judges: [] } as never })).toBe(1);
  });

  it("takes one to forty turns", () => {
    expect(SimulateInput.parse({ persona: "apurado" }).turns).toBe(15);
    expect(() => SimulateInput.parse({ persona: "apurado", turns: 41 })).toThrow();
  });
});
