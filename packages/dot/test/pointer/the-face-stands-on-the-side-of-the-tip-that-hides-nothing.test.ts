// The face and its words stand on the side of the tip that fits the screen and hides nothing of what is being explained.

import { describe, expect, it } from "vitest";

import { sideOf } from "../../src/pointer/person.js";

const SCREEN = { width: 1440, height: 900 };

describe("the side the face stands on", () => {
  it("is below and to the right of the tip, where it fits", () => {
    expect(sideOf({ x: 400, y: 300 }, null, SCREEN.width, SCREEN.height)).toEqual({ west: false, up: false });
  });

  it("goes to the left near the right edge, and above near the bottom", () => {
    expect(sideOf({ x: 1300, y: 300 }, null, SCREEN.width, SCREEN.height)).toEqual({ west: true, up: false });
    expect(sideOf({ x: 400, y: 860 }, null, SCREEN.width, SCREEN.height)).toEqual({ west: false, up: true });
  });

  it("stands above lines being explained that run below the tip, touching no more than the line the tip is in", () => {
    const lit = new DOMRect(40, 488, 640, 190);

    expect(sideOf({ x: 180, y: 500 }, lit, SCREEN.width, SCREEN.height)).toEqual({ west: false, up: true });
  });

  it("stays below when nothing fits clear of what is explained, rather than off the screen", () => {
    const everything = new DOMRect(0, 0, SCREEN.width, SCREEN.height);

    expect(sideOf({ x: 400, y: 300 }, everything, SCREEN.width, SCREEN.height)).toEqual({ west: false, up: false });
  });
});
