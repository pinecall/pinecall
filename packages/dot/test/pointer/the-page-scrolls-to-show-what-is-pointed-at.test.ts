// The page scrolls to show what is pointed at: a thing that fits, in the middle; a thing taller than the screen, from its start.

import { describe, expect, it } from "vitest";

import { scrollGoal } from "../../src/pointer/flight.js";

const SCREEN = 800;
const PAGE = 10_000;

describe("where the page scrolls to", () => {
  it("puts a thing that fits with its middle where it was asked", () => {
    expect(scrollGoal({ top: 1000, height: 200 }, 0, SCREEN, PAGE, 0.3)).toBe(1000 + 100 - 240);
  });

  it("shows a thing taller than the screen from its start, near the top, not from its middle", () => {
    expect(scrollGoal({ top: 1000, height: 2400 }, 500, SCREEN, PAGE, 0.3)).toBe(500 + 1000 - 80);
  });

  it("never scrolls above the page's top or past its end", () => {
    expect(scrollGoal({ top: 10, height: 100 }, 0, SCREEN, PAGE, 0.5)).toBe(0);
    expect(scrollGoal({ top: 9_900, height: 100 }, 0, SCREEN, PAGE, 0.3)).toBe(PAGE - SCREEN);
  });
});
