// A stage named in short on a class: "vendor/model", "vendor/voice", alone or with its options.

import { expect, it } from "vitest";

import { Agent } from "../../src/agent/agent.js";
import { modelOf, stageOf, voiceOf } from "../../src/agent/stage-names.js";
import { DeclarationRefused } from "../../src/agent/tools.js";
import { environmentOf } from "../../src/runtime/environment.js";
import { agent } from "../../src/agent/declaring.js";

it("reads a model as its vendor and its id, which keeps the slashes after the vendor's", () => {
  expect(modelOf("google/gemini-3.5-flash-lite")).toEqual({ provider: "google", model: "gemini-3.5-flash-lite" });
  expect(modelOf("livekit/openai/gpt-5-mini")).toEqual({ provider: "livekit", model: "openai/gpt-5-mini" });
  expect(modelOf("deepgram")).toEqual({ provider: "deepgram", model: "" });
});

it("takes a stage as a string, as a model with its options, or as the declaration already says it", () => {
  expect(stageOf("llm", "openai/gpt-5.4-mini")).toEqual({ provider: "openai", model: "gpt-5.4-mini" });
  expect(stageOf("llm", { model: "openai/gpt-5.4-mini", temperature: 0.3 })).toEqual({ provider: "openai", model: "gpt-5.4-mini", temperature: 0.3 });
  expect(stageOf("stt", { provider: "soniox", model: "stt-rt-v3" })).toEqual({ provider: "soniox", model: "stt-rt-v3" });
  expect(() => stageOf("llm", 4)).toThrow(DeclarationRefused);
});

it("takes a voice as vendor/voice, alone or with its options, and refuses one with no vendor", () => {
  expect(voiceOf("cartesia/f786b574")).toEqual({ provider: "cartesia", voiceId: "f786b574" });
  expect(voiceOf({ voice: "cartesia/f786b574", model: "sonic-2" })).toEqual({ provider: "cartesia", voiceId: "f786b574", model: "sonic-2" });
  expect(voiceOf({ provider: "cartesia", voiceId: "f786b574" })).toEqual({ provider: "cartesia", voiceId: "f786b574" });
  expect(() => voiceOf("katie")).toThrow(/vendor\/voice/);
});

it("is what a class declares of its stages, each by its vendor and its model", () => {
  @agent({ stt: { model: "deepgram/flux", endOfTurn: "stt" }, llm: "google/gemini-3.5-flash-lite", voice: "cartesia/f786b574" })
  class FrontDesk extends Agent {}
  expect(environmentOf(FrontDesk)).toMatchObject({
    stt: { provider: "deepgram", model: "flux", endOfTurn: "stt" },
    llm: { provider: "google", model: "gemini-3.5-flash-lite" },
    voice: { provider: "cartesia", voiceId: "f786b574" },
  });
});
