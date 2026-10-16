/** The Trace view's fold places every bar by an instant the log measured, held to the core's golden call. */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { decodeEntry } from "@pinecall/core/wire/codec";
import { apply, initialState } from "@pinecall/core/wire/reduce";
import { describe, expect, it } from "vitest";

import { traceOf, type TraceBar } from "../src/screens/call/trace-bars.js";

// The runtime's golden call, as the core holds it (packages/core/test/golden/).
const entries = (
  JSON.parse(readFileSync(fileURLToPath(new URL("../../packages/core/test/golden/call-log.json", import.meta.url)), "utf8")) as unknown[]
).map(decodeEntry);
const state = entries.reduce(apply, initialState());
const start = state.started_at ?? 0;
const trace = traceOf(entries, state);
const bars = (speech: string): TraceBar[] => trace.rows.find((row) => row.speech === speech)?.bars ?? [];

describe("the golden call read as a trace", () => {
  it("is one row per exchange, in the order the exchanges began", () => {
    expect(trace.rows.map((row) => row.speech)).toEqual(["speech_g0", "speech_01", "speech_02", "speech_r1", "speech_03", "speech_04", "speech_05"]);
    expect(trace.rows[1]?.said).toBe("Hola, quería pedir cita con la doctora Vidal.");
  });

  it("ends an LLM's bar at livekit's timestamp and reaches back its own duration, its first token ticked", () => {
    const llm = bars("speech_01").find((bar) => bar.kind === "llm");
    expect(llm?.to).toBeCloseTo(1786537510.87 - start, 6);
    expect(llm?.from).toBeCloseTo(1786537510.87 - 1.88 - start, 6);
    expect(llm?.tick).toBeCloseTo(1786537510.87 - 1.88 + 0.48 - start, 6);
  });

  it("draws the caller and the agent from the instants they started and stopped speaking", () => {
    const caller = bars("speech_01").find((bar) => bar.kind === "caller");
    expect(caller?.from).toBeCloseTo(1786537505.93 - start, 6);
    expect(caller?.to).toBeCloseTo(1786537508.56 - start, 6);
  });

  it("starts a tool where its call was logged and lasts what it reported", () => {
    const tool = bars("speech_02").find((bar) => bar.kind === "tool");
    expect(tool?.label).toBe("find_slots");
    expect(tool?.from).toBeCloseTo(1786537519.41 - start, 6);
    expect(tool?.to).toBeCloseTo(1786537519.41 + 0.212 - start, 6);
  });

  it("draws the interrupted reply and its cancelled voice as cut", () => {
    const cut = bars("speech_04").filter((bar) => bar.cut).map((bar) => bar.kind);
    expect(cut.sort()).toEqual(["agent", "voice"]);
  });

  it("runs the axis to the last thing logged", () => {
    expect(trace.span).toBeCloseTo((entries.at(-1)?.ts ?? 0) - start, 6);
  });
});

describe("a typed turn", () => {
  it("draws nothing, since nobody spoke it", () => {
    const typed = { ...state, turns: state.turns.map((turn) => ({ ...turn, metrics: {} })) };
    const kinds = traceOf(entries, typed).rows.flatMap((row) => row.bars.map((bar) => bar.kind));
    expect(kinds).not.toContain("caller");
    expect(kinds).not.toContain("agent");
  });
});
