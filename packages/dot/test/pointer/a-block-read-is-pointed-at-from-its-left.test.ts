// A block being read is pointed at from its left, the face in the margin and never on its words; above it, where the left has no room.

import { describe, expect, it } from "vitest";

import { besideOf, shownWhole } from "../../src/pointer/flight.js";

const at = (left: number, top: number, height = 80): Element => {
  const element = document.createElement("p");
  element.getBoundingClientRect = () => ({ left, top, height, width: 400, right: left + 400, bottom: top + height, x: left, y: top, toJSON: () => ({}) });
  return element;
};

describe("a block read", () => {
  it("is pointed at from its left, at its first line, the face to the left", () => {
    expect(besideOf(at(300, 200))).toEqual({ aim: { x: 298, y: 210 }, side: { west: true, up: false } });
  });

  it("is pointed at from above where its left has no room for the face", () => {
    expect(besideOf(at(20, 200))).toEqual({ aim: { x: 36, y: 196 }, side: { west: false, up: true } });
  });
});

describe("a block read, on the screen", () => {
  it("is shown whole, or it is scrolled to: one that only peeks in at the bottom is not seen", () => {
    expect(shownWhole(at(300, 200, 80))).toBe(true);
    expect(shownWhole(at(300, window.innerHeight - 30, 80))).toBe(false);
    expect(shownWhole(at(300, -20, 80))).toBe(false);
  });
});
