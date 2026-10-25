// The body is one of a few shapes, eases from one into another, and wobbles with the mood without ever reaching past its box.

import { describe, expect, it } from "vitest";

import { REACH, SHAPES, morphed, outlineOf, radii, shapeOf, wobbled } from "../../src/face/shape.js";

describe("the body's shape", () => {
  it("is a circle unless it names one of the others", () => {
    expect(shapeOf("blob")).toBe("blob");
    expect(shapeOf("star")).toBe("circle");
    expect(shapeOf(undefined)).toBe("circle");
  });

  it("stays inside its reach at rest and at its widest wobble, at any moment", () => {
    for (const shape of SHAPES) {
      for (const seconds of [0, 0.4, 1.3, 7.9]) {
        const rim = wobbled(radii(shape), 1, seconds);
        expect(Math.max(...rim), `${shape} at ${seconds}s`).toBeLessThanOrEqual(REACH);
        expect(Math.min(...rim), `${shape} at ${seconds}s`).toBeGreaterThan(30);
      }
    }
  });

  it("is still when it does not wobble, and moves when it does", () => {
    const rest = radii("circle");
    expect(wobbled(rest, 0, 3)).toEqual(rest);
    expect(wobbled(rest, 1, 3)).not.toEqual(rest);
  });

  it("eases from one shape into another, each point part of the way per frame", () => {
    const circle = radii("circle");
    const squircle = radii("squircle");
    const between = morphed(circle, squircle, 1 / 60);

    between.forEach((radius, at) => {
      const from = circle[at] ?? 0;
      const to = squircle[at] ?? 0;
      expect(Math.abs(radius - to)).toBeLessThanOrEqual(Math.abs(from - to));
    });
    expect(morphed(circle, squircle, 10)[0]).toBeCloseTo(squircle[0] ?? 0, 3);
  });

  it("is drawn as one smooth closed path round the middle", () => {
    const d = outlineOf(radii("blob"));
    expect(d).toMatch(/^M [\d.]+ [\d.]+ C /);
    expect(d.endsWith(" Z")).toBe(true);
    expect(d.match(/ C /g)).toHaveLength(48);
  });
});
