// A box that scrolls inside the page keeps its own scroll-padding-top clear: a bar stuck inside it covers that much, and what is scrolled to sits below it.

import { afterEach, describe, expect, it } from "vitest";

import { paddingOf, scrollGoal } from "../../src/pointer/flight.js";

afterEach(() => {
  document.body.innerHTML = "";
});

describe("a box that scrolls", () => {
  it("says how much of its top its own scroll-padding keeps clear, and nothing when it says none", () => {
    document.body.innerHTML = `<div id="a" style="overflow:auto;scroll-padding-top:56px"></div><div id="b" style="overflow:auto"></div>`;
    expect(paddingOf(document.getElementById("a")!)).toBe(56);
    expect(paddingOf(document.getElementById("b")!)).toBe(0);
  });

  it("scrolls what is pointed at to below that padding, as below the page's header", () => {
    const PADDING = 56;
    const goal = scrollGoal({ top: 30, height: 40 }, 500, 800, 10_000, 0.42, PADDING);
    expect(30 - (goal - 500)).toBeGreaterThanOrEqual(PADDING);
  });
});
