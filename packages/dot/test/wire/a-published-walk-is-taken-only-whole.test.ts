// A walk the agent published is taken by the page only whole: each step with its audio, its timed words and its beats.

import { describe, expect, it } from "vitest";

import { clock, macroOf, walksOf } from "../../src/wire/index.js";

const STEP = {
  say: "Up here are our services.",
  audio: "https://gw/v1/lines/9f2c.mp3",
  durationMs: 1610,
  words: [{ text: "Up", startMs: 325, endMs: 495 }],
  beats: [{ word: "Up", do: "point", find: ["link", "Services"] }],
};

describe("the walks a page reads", () => {
  it("are each a name, a title and steps it can play", () => {
    expect(walksOf({ walks: [{ name: "tour", title: "Site tour", when: "asked", steps: [STEP] }] })).toEqual([
      { name: "tour", title: "Site tour", when: "asked", steps: [STEP] },
    ]);
  });

  it("leave out a walk with a step that is not one: no audio, an audio that is no URL, a beat that types", () => {
    const broken = [{ ...STEP, audio: undefined }, { ...STEP, audio: "javascript:alert(1)" }, { ...STEP, beats: [{ word: "Up", do: "type" }] }];

    for (const step of broken) expect(walksOf({ walks: [{ name: "tour", title: "Site tour", steps: [step] }] })).toEqual([]);
    expect(walksOf(null)).toEqual([]);
    expect(walksOf({ walks: "tour" })).toEqual([]);
  });
});

describe("a macro file", () => {
  it("keeps the title its button shows, and none when it gives none", () => {
    const steps = [{ say: "Hi.", beats: [] }];

    expect(macroOf("tour", { title: "Site tour", steps }).title).toBe("Site tour");
    expect(macroOf("tour", { steps }).title).toBeUndefined();
  });
});

describe("a length", () => {
  it("reads as a clock does", () => {
    expect(clock(38_400)).toBe("0:38");
    expect(clock(61_000)).toBe("1:01");
  });
});
