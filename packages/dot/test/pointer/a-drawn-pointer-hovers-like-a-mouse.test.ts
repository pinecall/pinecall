// The site's :hover rules are mirrored onto an attribute, and the pointer flies a still-to-still path with a slight arc.

import { afterEach, describe, expect, it } from "vitest";

import { along, flightMs, minJerk } from "../../src/pointer/flight.js";
import { mirrored } from "../../src/pointer/hover.js";

afterEach(() => {
  document.head.innerHTML = "";
});

describe("the mirrored hovers", () => {
  it("copies every :hover rule with the attribute in its place, inside its media query too", () => {
    const style = document.createElement("style");
    style.textContent = "nav a:hover { color: red; } @media (min-width: 1px) { .card:hover { opacity: 0.5; } } p { color: blue; }";
    document.head.append(style);

    const css = mirrored(document);
    expect(css).toContain("nav a[data-pc-hover]");
    expect(css).toMatch(/@media \(min-width: 1px\) \{ \.card\[data-pc-hover\]/);
    expect(css).not.toContain("color: blue");
  });
});

describe("the flight", () => {
  it("starts and ends still, and takes longer the farther it goes, up to a ceiling", () => {
    expect(minJerk(0)).toBe(0);
    expect(minJerk(1)).toBe(1);
    expect(flightMs(100, 1000)).toBeLessThan(flightMs(800, 1000));
    expect(flightMs(5000, 1000)).toBe(flightMs(1000, 1000));
  });

  it("lands exactly where it was sent, bending off the straight line on the way", () => {
    const from = { x: 0, y: 0 };
    const to = { x: 400, y: 0 };

    expect(along(from, to, 1)).toEqual(to);
    expect(Math.abs(along(from, to, 0.5).y)).toBeGreaterThan(10);
  });
});
