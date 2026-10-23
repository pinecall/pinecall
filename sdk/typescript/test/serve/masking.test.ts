// What a served process prints: the values its agent declared private, masked as the call's log masks them.

import { describe, expect, it } from "vitest";

import type { AgentOptions } from "../../src/client/index.js";
import { Masking } from "../../src/serve/masking.js";
import type { Entry } from "../../src/wire/envelope.js";

const DECLARED = {
  tools: [{ name: "takeMessage", description: "d", parameters: {}, pii: ["name"] }],
  stateFields: [{ name: "patient", visibility: "pii" }],
} as unknown as Pick<AgentOptions, "tools" | "stateFields">;

function entry(type: string, data: Record<string, unknown>): Entry {
  return { seq: 3, ts: 1, call: "CA_1", agent: "desk", type, ephemeral: false, data };
}

const ASKED = entry("tool.call", { call_id: "tc_1", name: "takeMessage", arguments: { name: "Ana Lopez", about: "Ana Lopez wants a refund" } });

describe("what a tool call prints", () => {
  it("masks the argument the tool names and the value wherever another argument repeats it", () => {
    expect(new Masking(DECLARED).entry(ASKED).data["arguments"]).toEqual({ name: "***", about: "*** wants a refund" });
  });
});

describe("what comes after the tool call", () => {
  it("masks the value in the state that holds it, in what the tool answered and in a line the agent logged", () => {
    const masking = new Masking(DECLARED);
    masking.entry(ASKED);

    expect(masking.entry(entry("state.changed", { state: { message: { name: "Ana Lopez" }, stage: "done" }, changed: [] })).data["state"]).toEqual({
      message: { name: "***" },
      stage: "done",
    });
    expect(masking.entry(entry("tool.result", { call_id: "tc_1", name: "takeMessage", output: "Saved for Ana Lopez." })).data["output"]).toBe("Saved for ***.");
    expect(masking.entry(entry("custom", { name: "booked", data: { who: "Ana Lopez" } })).data["data"]).toEqual({ who: "***" });
  });

  it("masks a state field declared private whole, before any tool call", () => {
    const state = { patient: { id: 7 }, stage: "ask" };
    expect(new Masking(DECLARED).entry(entry("state.changed", { state, changed: ["patient"] })).data["state"]).toEqual({ patient: "***", stage: "ask" });
  });

  it("masks a value only where it stands as a whole word, in any script", () => {
    const masking = new Masking(DECLARED);
    masking.entry(entry("tool.call", { call_id: "tc_9", name: "takeMessage", arguments: { name: "Ana" } }));
    const said = "Banana and Anabel, but Ana's, Ana, (Ana) and José Ana, Anaïs";

    expect(masking.entry(entry("custom", { name: "x", data: { said } })).data["data"]).toEqual({
      said: "Banana and Anabel, but ***'s, ***, (***) and José ***, Anaïs",
    });
  });

  it("never learns a value shorter than three characters, and learns one of three", () => {
    const short = new Masking(DECLARED);
    for (const name of ["7", "ok", "Al", "  Bo ", ""]) {
      short.entry(entry("tool.call", { call_id: "tc_9", name: "takeMessage", arguments: { name } }));
    }
    const line = entry("custom", { name: "x", data: { who: "Al ok 7 Bo" } });
    expect(short.entry(line)).toEqual(line);

    const three = new Masking(DECLARED);
    three.entry(entry("tool.call", { call_id: "tc_9", name: "takeMessage", arguments: { name: "Ann" } }));
    expect(three.entry(entry("custom", { name: "x", data: { who: "Ann" } })).data["data"]).toEqual({ who: "***" });
  });

  it("leaves what was said alone, and an entry with nothing private is the entry itself", () => {
    const masking = new Masking(DECLARED);
    masking.entry(ASKED);
    const said = entry("turn.user", { speech_id: "s1", text: "Soy Ana Lopez" });
    const quiet = entry("state.changed", { state: { stage: "ask" }, changed: ["stage"] });

    expect(masking.entry(said)).toBe(said);
    expect(masking.entry(quiet).data["state"]).toEqual({ stage: "ask" });
    expect(new Masking({}).entry(ASKED)).toBe(ASKED);
  });
});
