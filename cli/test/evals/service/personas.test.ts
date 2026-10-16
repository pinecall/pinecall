/** An agent's callers against the gateway: one written whole or merged, Pinecall's switched and never dropped, callers generated and kept. */

import { describe, expect, it } from "vitest";

import { UsageError } from "../../../src/errors.js";
import * as personas from "../../../src/evals/service/personas.js";
import { answer } from "../../support/gateway.js";
import { testContext } from "../../support/context.js";
import { A_PERSONA } from "../../support/fixtures.js";

const LIBRARY = { ...A_PERSONA, name: "confused-elder", owner: "pinecall", on: false };

describe("a persona of the agent's own", () => {
  it("added needs a goal and a style, and a name the gateway takes", async () => {
    answer("get", "/v1/agents/:slug/personas", { personas: [] });
    const { ctx } = testContext();
    await expect(personas.writePersona(ctx, "front-desk", "apurado", "add", {})).rejects.toThrow("a persona needs --goal and --style");
    await expect(personas.writePersona(ctx, "front-desk", "Apurado Luis", "add", { goal: "g", style: "s" })).rejects.toThrow(/no name for a caller/);
  });

  it("edited keeps every field not named, the behavior merged", async () => {
    answer("get", "/v1/agents/:slug/personas", { personas: [A_PERSONA] });
    const sent = answer("put", "/v1/agents/:slug/personas/:name", { personas: [A_PERSONA] });
    const { ctx } = testContext();
    await personas.writePersona(ctx, "front-desk", "apurado", "edit", personas.WritePersonaInput.parse({ speed: 1.3, llm: "haiku", ambience: "street", backgroundNoise: 12 }));
    expect(sent[0]!.path).toBe("/v1/agents/front-desk/personas/apurado");
    expect(sent[0]!.body).toEqual({
      goal: A_PERSONA.goal,
      style: A_PERSONA.style,
      about: "",
      facts: { name: "Luis" },
      state: {},
      llm: "anthropic/claude-haiku-5-5",
      tts: null,
      voice: null,
      expects: [],
      tags: [],
      behavior: { ...A_PERSONA.behavior, speed: 1.3, ambience: "street", interferer_db: 12 },
    });
  });

  it("renamed is written under the new name, with the old one said", async () => {
    answer("get", "/v1/agents/:slug/personas", { personas: [A_PERSONA] });
    const sent = answer("put", "/v1/agents/:slug/personas/:name", { personas: [] });
    const { ctx } = testContext();
    await personas.writePersona(ctx, "front-desk", "apurado", "edit", { rename: "in-a-hurry" });
    expect(sent[0]!.path).toBe("/v1/agents/front-desk/personas/in-a-hurry");
    expect(sent[0]!.body).toMatchObject({ was: "apurado" });
  });

  it("an empty field resets it to the runtime's default", async () => {
    answer("get", "/v1/agents/:slug/personas", { personas: [{ ...A_PERSONA, voice: "cartesia-luis" }] });
    const sent = answer("put", "/v1/agents/:slug/personas/:name", { personas: [] });
    const { ctx } = testContext();
    await personas.writePersona(ctx, "front-desk", "apurado", "edit", { voice: "" });
    expect(sent[0]!.body).toMatchObject({ voice: null });
  });
});

describe("Pinecall's personas", () => {
  it("are switched, never written over nor dropped", async () => {
    answer("get", "/v1/agents/:slug/personas", { personas: [LIBRARY, A_PERSONA] });
    const sent = answer("put", "/v1/agents/:slug/personas/:name", { personas: [] });
    const { ctx } = testContext();
    await personas.switchPersona(ctx, "front-desk", "confused-elder", true);
    expect(sent[0]!.body).toEqual({ on: true });
    await expect(personas.writePersona(ctx, "front-desk", "confused-elder", "edit", { goal: "x" })).rejects.toThrow(personas.PINECALLS("confused-elder"));
    await expect(personas.dropPersona(ctx, "front-desk", "confused-elder")).rejects.toThrow(/never dropped/);
    await expect(personas.switchPersona(ctx, "front-desk", "apurado", false)).rejects.toBeInstanceOf(UsageError);
  });
});

describe("generated callers", () => {
  it("are kept as the agent's own only with save", async () => {
    const proposed = { name: "price-shopper", about: "", goal: "compare prices", style: "curt", facts: {}, expects: [], tags: [], behavior: A_PERSONA.behavior };
    const generated = answer("post", "/v1/agents/:slug/personas/generate", { personas: [proposed], evals: 1, cost_usd: 0.002 });
    const kept = answer("put", "/v1/agents/:slug/personas/:name", { personas: [] });
    const { ctx } = testContext();
    await personas.generatePersonas(ctx, "front-desk", personas.GenerateInput.parse({ n: 1, fromCall: "call_9" }));
    expect(kept).toHaveLength(0);
    const saved = await personas.generatePersonas(ctx, "front-desk", personas.GenerateInput.parse({ n: 1, save: true }));
    expect(generated[0]!.body).toEqual({ n: 1, from_call: "call_9" });
    expect(kept[0]!.path).toBe("/v1/agents/front-desk/personas/price-shopper");
    expect(saved.saved).toBe(true);
  });

  it("takes one to ten", () => {
    expect(() => personas.GenerateInput.parse({ n: 11 })).toThrow("generate takes how many callers, 1 to 10");
  });
});

describe("facts", () => {
  it("are what=said, repeated", () => {
    expect(personas.factsOf(["their phone=305 555 0101", "name = Luis"])).toEqual({ "their phone": "305 555 0101", name: "Luis" });
    expect(() => personas.factsOf(["Luis"])).toThrow(/a fact is what=said/);
  });
});
