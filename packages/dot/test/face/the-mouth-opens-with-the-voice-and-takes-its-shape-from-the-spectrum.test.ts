// Loudness opens the jaw and the spectrum shapes the lips: hiss shows teeth, a front vowel widens, a back vowel rounds.

import { describe, expect, it } from "vitest";

import { levelOf, outline, peakAfter, spoken, type Bands } from "../../src/face/mouth.js";

const FRONT: Bands = { low: 1, mid: 1, high: 3, sib: 0.1 };
const BACK: Bands = { low: 9, mid: 0.5, high: 0.05, sib: 0.01 };
const HISS: Bands = { low: 0.2, mid: 0.2, high: 0.6, sib: 3 };
const VOWEL: Bands = { low: 1, mid: 2, high: 1, sib: 0.05 };

describe("the mouth a frame of voice asks for", () => {
  it("stays shut in silence, whatever the spectrum", () => {
    const quiet = spoken(0, HISS);

    expect(quiet.open).toBe(0);
    expect(quiet.teeth).toBe(0);
    expect(quiet.round).toBe(0);
  });

  it("opens further the louder the voice", () => {
    expect(spoken(0.9, VOWEL).open).toBeGreaterThan(spoken(0.4, VOWEL).open);
  });

  it("shows teeth and opens little on a hiss, S or T", () => {
    const s = spoken(0.8, HISS);

    expect(s.teeth).toBeGreaterThan(0.8);
    expect(s.open).toBeLessThan(spoken(0.8, VOWEL).open);
  });

  it("widens on a front vowel and rounds on a back one", () => {
    const ee = spoken(0.8, FRONT);
    const oo = spoken(0.8, BACK);

    expect(ee.width).toBeGreaterThan(oo.width);
    expect(oo.round).toBeGreaterThan(0.5);
    expect(ee.round).toBe(0);
  });
});

describe("the automatic gain", () => {
  it("takes a louder frame at once and lets a quiet stretch decay slowly, never below -30 dB", () => {
    expect(peakAfter(-20, -10, 0.016)).toBe(-10);
    expect(peakAfter(-10, -40, 1)).toBe(-14);
    expect(peakAfter(-29, -60, 10)).toBe(-30);
  });

  it("calls the loudest recent frame fully open and silence shut", () => {
    expect(levelOf(-12, -12)).toBe(1);
    expect(levelOf(-60, -12)).toBe(0);
  });
});

describe("the outline", () => {
  it("is one closed path between the corners, and a round mouth is narrower than a wide one", () => {
    const wide = outline({ ...spoken(0.8, FRONT), shift: 0 });
    const round = outline({ ...spoken(0.8, BACK), shift: 0 });

    expect(wide.d).toMatch(/^M [\d.]+ [\d.]+ C .+ C .+ Z$/);
    expect(round.half).toBeLessThan(wide.half);
  });

  it("drops the lower lip as it opens", () => {
    const shut = outline({ open: 0, width: 0.5, round: 0, teeth: 0, smile: 0, shift: 0 });
    const open = outline({ open: 1, width: 0.5, round: 0, teeth: 0, smile: 0, shift: 0 });

    expect(open.down).toBeGreaterThan(shut.down + 10);
  });
});
