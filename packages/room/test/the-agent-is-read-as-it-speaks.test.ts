// Karaoke from the log: the reply in progress is found, and a word is lit when the voice says it.

import { type Entry } from "../src/wire/envelope.js";
import { describe, expect, it } from "vitest";

import { joined, litAt, sayingOf, soundedBy } from "../src/karaoke.js";

let seq = 0;
const entry = (type: string, data: Record<string, unknown>): Entry => ({
  seq: (seq += 1),
  ts: 1_790_000_000 + seq,
  call: "call_x",
  agent: "bernardo",
  type,
  ephemeral: type.endsWith("transcript"),
  data,
});
const word = (text: string, start: number | null, speech = "sp_2"): Entry =>
  entry("agent.transcript", { speech_id: speech, text, final: false, ...(start === null ? {} : { start, end: start + 0.3 }) });
const closed = (speech: string, text: string): Entry =>
  entry("turn.agent", { speech_id: speech, text, interrupted: false, metrics: {} });

describe("the agent is read as it speaks", () => {
  it("finds the reply in progress: every delta since the last closed turn", () => {
    const saying = sayingOf([
      word("Old ", 0, "sp_1"),
      closed("sp_1", "Old"),
      entry("turn.user", { speech_id: "sp_u", text: "Thursday", metrics: {} }),
      word("Two ", 0),
      entry("agent.state", { state: "speaking" }),
      word("or ", 0.4),
      word("four? ", 0.7),
    ]);
    expect(saying?.speech).toBe("sp_2");
    expect(saying?.words.map((w) => w.text)).toEqual(["Two ", "or ", "four? "]);
  });

  it("finds nobody mid-reply once the turn closed or a final delta came", () => {
    expect(sayingOf([word("Two ", 0), closed("sp_2", "Two")])).toBeNull();
    expect(sayingOf([word("Two ", 0), entry("agent.transcript", { speech_id: "sp_2", text: "", final: true })])).toBeNull();
    expect(sayingOf([])).toBeNull();
  });

  it("lights a word when the clock reaches it, and never ahead of one before it", () => {
    const words = [
      { text: "Two ", start: 0 },
      { text: "or ", start: 0.4 },
      { text: "four? ", start: 0.7 },
    ];
    expect([0, 399, 400, 5000].map((ms) => soundedBy(words, ms))).toEqual([1, 1, 2, 3]);
    expect(soundedBy([{ text: "a", start: 2 }, { text: "b", start: null }], 0)).toBe(0);
    expect(litAt({ speech: "sp_2", words }, 450)).toEqual({ lit: "Two or ", coming: "four? " });
  });

  it("lights a written reply's tokens the moment they arrive, joined as they came", () => {
    const tokens = [" or", " fo", "ur?"].map((text) => ({ text, start: null }));
    const words = [{ text: "Two", start: null }, ...tokens];
    expect(soundedBy(words, 0)).toBe(4);
    expect(joined(words)).toBe("Two or four?");
  });
});
