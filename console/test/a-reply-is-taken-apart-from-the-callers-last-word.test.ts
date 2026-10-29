/** The Inspector's live trace folds the golden call into one exchange per caller's turn, every bar by an instant the log measured. */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { decodeEntry } from "@pinecall/core/wire/codec";
import { describe, expect, it } from "vitest";

import { feltOf, traceOf } from "../src/screens/talk/exchanges.js";

// The runtime's golden call, as the core holds it (packages/core/test/golden/).
const entries = (JSON.parse(readFileSync(fileURLToPath(new URL("../../packages/core/test/golden/call-log.json", import.meta.url)), "utf8")) as unknown[]).map(decodeEntry);
const trace = traceOf(entries, false);
const exchange = (id: string) => trace.exchanges.find((ex) => ex.id === id);

describe("the golden call read as the caller lived it", () => {
  it("is one exchange per turn of the caller's, in order, the greeting none", () => {
    expect(trace.exchanges.map((ex) => ex.id)).toEqual(["speech_01", "speech_02", "speech_03", "speech_04", "speech_05"]);
    expect(exchange("speech_01")?.said).toBe("Hola, quería pedir cita con la doctora Vidal.");
  });

  it("takes a reply's wait apart as the wire measured it, the rest named network", () => {
    expect(exchange("speech_01")?.e2e).toBe(0.87);
    expect(exchange("speech_01")?.stages).toEqual({ hears: 0.41, thinks: 0.48, speaks: 0.19, other: null });
    expect(exchange("speech_02")?.stages?.other).toBeCloseTo(0.64, 6);
    expect(feltOf(trace)).toEqual([870, 1720, 940, 1080, 820]);
  });

  it("lays a tool on its own lane from the instant it was called to the instant it answered", () => {
    const tool = exchange("speech_02")?.bars.find((bar) => bar.lane === "tools");
    expect(tool?.label).toBe("find_slots");
    expect(tool?.from).toBeCloseTo(1.06, 2);
    expect(tool?.to).toBeCloseTo(1.27, 2);
  });

  it("names the three models from their metadata and counts what they did", () => {
    expect(trace.models).toEqual({ hears: "soniox · stt-rt-v5", thinks: "anthropic · claude-haiku-5-5", speaks: "elevenlabs · eleven_flash_v2_5" });
    expect(trace.counts.tools).toBe(2);
    expect(trace.counts.cut).toBe(1);
    expect(trace.counts.tokensIn).toBe(17551);
  });

  it("is still, nothing happening now, once the call has ended", () => {
    expect(traceOf(entries, true).now).toBeNull();
    expect(traceOf(entries, true).waitingSince).toBeNull();
  });

  it("counts the caller's wait from the moment they stopped, while the agent has not been heard", () => {
    const stopped = entries.findIndex((entry) => entry.type === "turn.user");
    const sofar = traceOf(entries.slice(0, stopped + 1), true);
    expect(sofar.waitingSince).not.toBeNull();
    expect(sofar.now).toBe("hears");
    expect(sofar.exchanges.at(-1)?.done).toBe(false);
  });
});
