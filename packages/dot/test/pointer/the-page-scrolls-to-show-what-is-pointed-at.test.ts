// The page scrolls to show what is pointed at: a thing that fits, whole; a thing taller than the screen, from its start; never under the site's header.

import { describe, expect, it } from "vitest";

import { scrollGoal } from "../../src/pointer/flight.js";

const SCREEN = 800;
const PAGE = 10_000;

describe("where the page scrolls to", () => {
  it("puts a thing that fits with its middle where it was asked", () => {
    expect(scrollGoal({ top: 1000, height: 200 }, 0, SCREEN, PAGE, 0.3)).toBe(1000 + 100 - 240);
  });

  it("shows a thing taller than the screen from its start, just under the top, not from its middle", () => {
    expect(scrollGoal({ top: 1000, height: 2400 }, 500, SCREEN, PAGE, 0.3)).toBe(500 + 1000 - 16);
  });

  it("shows a thing that fits whole, never cut at the top or the bottom to stand at its spot", () => {
    // Its middle at 30% would put its top above the screen: it comes down until it is whole.
    const goal = scrollGoal({ top: 1000, height: 600 }, 0, SCREEN, PAGE, 0.3);
    const top = 1000 - goal;
    expect(top).toBeGreaterThanOrEqual(16);
    expect(top + 600).toBeLessThanOrEqual(SCREEN - 16);
  });

  it("never scrolls above the page's top or past its end", () => {
    expect(scrollGoal({ top: 10, height: 100 }, 0, SCREEN, PAGE, 0.5)).toBe(0);
    expect(scrollGoal({ top: 9_900, height: 100 }, 0, SCREEN, PAGE, 0.3)).toBe(PAGE - SCREEN);
  });

  it("counts the site's own header out of the screen: what it scrolls to sits below it", () => {
    const HEADER = 80;
    const FREE = SCREEN - HEADER;
    expect(scrollGoal({ top: 1000, height: 200 }, 0, SCREEN, PAGE, 0.3, HEADER)).toBe(1000 + 100 - HEADER - FREE * 0.3);
    // A section taller than the free part starts just below the header, never under it.
    expect(scrollGoal({ top: 1000, height: 2400 }, 500, SCREEN, PAGE, 0.3, HEADER)).toBe(500 + 1000 - HEADER - 16);
  });
});
