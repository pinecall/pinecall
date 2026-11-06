/** A comparison the gateway refused whole: its reasons said once each, and no table asked for. */

import { describe, expect, it } from "vitest";

import { UsageError } from "../../../src/errors.js";
import * as comparison from "../../../src/evals/service/comparison.js";
import { SimulateInput } from "../../../src/evals/service/simulation.js";
import { answer } from "../../support/gateway.js";
import { testContext } from "../../support/context.js";
import { A_PERSONA } from "../../support/fixtures.js";

const NOBODY_HOLDS = "no app holds agent dentist: `pinecall start` holds it from a terminal, `pinecall deploy` runs it on Pinecall";

describe("a comparison with nothing placed", () => {
  it("fails with the gateway's reason, said once, and never asks for a table that does not exist", async () => {
    const against = [{ llm: "google/gemini-3.5-flash-lite" }, { llm: "openai/gpt-5-mini" }];
    answer("post", "/v1/simulations/compare", {
      comparison: "cmp_1",
      voice: false,
      calls: [],
      refused: against.map((values) => ({ persona: A_PERSONA.name, against: values, why: NOBODY_HOLDS })),
    });
    const asked = answer("get", "/v1/simulations/compare/:id", {});
    const { ctx } = testContext();
    const placed = comparison.compare(ctx, "dentist", A_PERSONA, SimulateInput.parse({ persona: A_PERSONA.name }), against);
    await expect(placed).rejects.toBeInstanceOf(UsageError);
    await expect(placed).rejects.toThrow(`no call was placed: all 2 rows were refused — ${NOBODY_HOLDS}`);
    expect(asked).toEqual([]);
  });
});
