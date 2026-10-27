// A page read aloud is recorded ahead, a few parts at a time, each text once: the door keeps them, so the reading starts at once; a part the door fails is left for the reading.

import { describe, expect, it } from "vitest";

import { recordAhead } from "../../src/tutor/walks.js";
import type { WalkStep } from "../../src/wire/index.js";

const said = (say: string): WalkStep => ({ say, beats: [], live: true });

describe("a page recorded ahead", () => {
  it("asks the door for every text it says, once each, never more than three at a time, and counts what it got", async () => {
    const asked: string[] = [];
    let open = 0;
    let most = 0;
    const steps: WalkStep[] = [said("Uno."), said("Dos."), { press: "Run" }, said("Uno."), said("Tres."), said("Cuatro."), said("Cinco.")];

    const done = await recordAhead(steps, async (text) => {
      asked.push(text);
      open += 1;
      most = Math.max(most, open);
      await new Promise((resolve) => setTimeout(resolve, 5));
      open -= 1;
      if (text === "Tres.") throw new Error("the door failed");
      return { say: text };
    });

    expect([...asked].sort()).toEqual(["Cinco.", "Cuatro.", "Dos.", "Tres.", "Uno."]);
    expect(most).toBe(3);
    expect(done).toBe(4);
  });
});
