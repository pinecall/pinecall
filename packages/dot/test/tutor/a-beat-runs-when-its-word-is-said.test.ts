// A macro step's beats run as their words are said, each once, in the reply that follows the step, and never in another.

import { describe, expect, it } from "vitest";

import { Player, placesOf } from "../../src/tutor/macro.js";
import type { Step } from "../../src/wire/index.js";

const STEP: Step = {
  type: "macro.step",
  macro: "tour",
  step: 1,
  say: "Pricing is simple. There are three plans, and most families pick Family Care.",
  beats: [
    { word: "Pricing", do: "scroll_to", find: ["region", "Pricing"] },
    { word: "most", do: "highlight", find: ["article", "Family Care"] },
    { word: "Family", do: "point", find: ["button", "Choose Family Care"] },
  ],
};

describe("where a beat sits", () => {
  it("is the index of its word, the n-th time it is said, case and punctuation aside", () => {
    expect(placesOf(STEP)).toEqual([0, 8, 11]);
    expect(placesOf({ say: "The plan and the price", beats: [{ word: "the", nth: 2, do: "here" }] })).toEqual([3]);
  });

  it("is -1 for a word the sentence never says that many times", () => {
    expect(placesOf({ say: "The plan", beats: [{ word: "the", nth: 2, do: "here" }] })).toEqual([-1]);
  });
});

describe("a step played", () => {
  it("runs nothing until a reply after it starts, then each beat as its word is lit", () => {
    const player = new Player();
    player.arm(STEP, "speech_before");

    expect(player.due("speech_before", "Hi there")).toEqual([]);
    expect(player.due("speech_2", "Pricing").map((beat) => beat.do)).toEqual(["scroll_to"]);
    expect(player.due("speech_2", "Pricing is simple. There are three plans, and")).toEqual([]);
    expect(player.due("speech_2", "Pricing is simple. There are three plans, and most families pick").map((beat) => beat.do)).toEqual(["highlight"]);
    expect(player.due("speech_2", "Pricing is simple. There are three plans, and most families pick Family").map((beat) => beat.do)).toEqual(["point"]);
    expect(player.due("speech_2", "Pricing is simple. There are three plans, and most families pick Family Care.")).toEqual([]);
  });

  it("is over when its reply ends: the beats left are never run", () => {
    const player = new Player();
    player.arm(STEP, null);
    player.due("speech_2", "Pricing");

    expect(player.due(null, "")).toEqual([]);
    expect(player.armed).toBe(false);
    expect(player.due("speech_3", "Pricing is simple. There are three plans, and most")).toEqual([]);
  });

  it("is replaced by the next step, and dropped when the tutor stops", () => {
    const player = new Player();
    player.arm(STEP, null);
    player.arm({ ...STEP, step: 2 }, null);
    player.drop();

    expect(player.armed).toBe(false);
  });
});
