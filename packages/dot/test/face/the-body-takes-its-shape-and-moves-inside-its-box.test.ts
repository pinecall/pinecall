// The body is one of a few shapes, eases from one into another, and leaves room in its box for the motion of the whole body.

import { describe, expect, it } from "vitest";

import { REACH, SHAPES, morphed, outlineOf, radii, shapeOf } from "../../src/face/shape.js";

describe("the body's shape", () => {
  it("is a circle unless it names one of the others", () => {
    expect(shapeOf("blob")).toBe("blob");
    expect(shapeOf("star")).toBe("circle");
    expect(shapeOf(undefined)).toBe("circle");
  });

  it("stays inside its reach, round enough everywhere to read as one soft body", () => {
    for (const shape of SHAPES) {
      const rim = radii(shape);
      expect(Math.max(...rim), shape).toBeLessThanOrEqual(REACH);
      expect(Math.min(...rim) / Math.max(...rim), shape).toBeGreaterThan(0.8);
    }
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
