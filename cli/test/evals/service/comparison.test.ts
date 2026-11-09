/** A comparison the gateway refused whole: its reasons said once each, and no table asked for; and one whose calls wait their turn, which is read to its end. */

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

// The fault this guards: with nothing placed yet the verb took a comparison for refused, though its
// calls only waited for a place on the org's line.
describe("a comparison whose calls wait their turn", () => {
  it("asks for the repeats it was given, is not taken for refused, and answers the table once nothing waits", async () => {
    const against = [{}, { llm: "google/gemini-3.5-flash-lite" }];
    const placed = answer("post", "/v1/simulations/compare", { comparison: "cmp_2", voice: false, calls: [], refused: [], waiting: 6 });
    const refused = [{ persona: A_PERSONA.name, against: against[1], why: "the org has used 10 of its 10 simulations in the sandbox" }];
    answer("get", "/v1/simulations/compare/:id", { comparison: "cmp_2", agent: "dentist", persona: A_PERSONA.name, personas: [A_PERSONA.name], voice: false, rows: [], repeats: 3, planned: 6, waiting: 0, refused });
    const { ctx } = testContext();
    const done = await comparison.compare(ctx, "dentist", A_PERSONA, SimulateInput.parse({ persona: A_PERSONA.name, repeats: 3 }), against);
    expect(placed.map((sent) => (sent.body as { repeats?: number }).repeats)).toEqual([3]);
    expect(done.comparison).toBe("cmp_2");
    // What was refused after the answer is the table's to say: the first answer knew none of it.
    expect(done.refused).toEqual(refused);
  });

  it("names no repeats when the caller rings once, as a gateway from before them expects", async () => {
    const placed = answer("post", "/v1/simulations/compare", { comparison: "cmp_3", voice: false, calls: [], refused: [], waiting: 1 });
    answer("get", "/v1/simulations/compare/:id", { comparison: "cmp_3", agent: "dentist", persona: A_PERSONA.name, personas: [A_PERSONA.name], voice: false, rows: [] });
    const { ctx } = testContext();
    await comparison.compare(ctx, "dentist", A_PERSONA, SimulateInput.parse({ persona: A_PERSONA.name }), [{}, { llm: "openai/gpt-5-mini" }]);
    expect(placed.map((sent) => "repeats" in (sent.body as object))).toEqual([false]);
  });
});
