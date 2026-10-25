// The walks fan out from a small button beside the resting face, in an arc toward the page, and a pick plays one.

import { afterEach, describe, expect, it, vi } from "vitest";

import { Menu, OFFERED_MS, STEP, fanned } from "../../src/pointer/menu.js";

afterEach(() => {
  document.body.innerHTML = "";
  document.head.innerHTML = "";
});

function aMenu(picked: number[]): Menu {
  return new Menu(document, (part) => document.body.append(part), {
    dock: "right",
    label: "Walks",
    face: () => ({ at: { x: 900, y: 700 }, radius: 36 }),
    onPick: (index) => picked.push(index),
  });
}

describe("the walks' menu", () => {
  it("fans its pills from beside the face to above it, toward the page, the nearest first", () => {
    const points = fanned(3, { x: 900, y: 700 }, 36, "right");

    expect(points.every((point) => point.x < 900 && point.y < 700)).toBe(true);
    expect(points[0]!.y).toBeGreaterThan(points[2]!.y);
    expect(fanned(3, { x: 100, y: 700 }, 36, "left").every((point) => point.x > 100)).toBe(true);
  });

  it("never sets two pills closer than a step, however many there are, the higher ones nearer the face", () => {
    for (const count of [2, 3, 6]) {
      const points = fanned(count, { x: 900, y: 700 }, 36, "right");
      points.slice(1).forEach((point, at) => {
        expect(points[at]!.y - point.y).toBeGreaterThanOrEqual(STEP);
        expect(point.x).toBeGreaterThanOrEqual(points[at]!.x);
      });
    }
  });

  it("shows its button only with walks to offer, and plays the one picked", () => {
    const picked: number[] = [];
    const menu = aMenu(picked);
    const button = document.querySelector<HTMLButtonElement>(".pc-walks");
    expect(button?.hidden).toBe(true);

    menu.offer([{ title: "Site tour", ms: 38_000 }, { title: "Pricing", ms: 20_000 }]);
    menu.available(true);
    expect(button?.hidden).toBe(false);
    button?.click();
    const pills = [...document.querySelectorAll<HTMLButtonElement>(".pc-pill")];
    expect(pills.map((pill) => pill.textContent)).toEqual(["Site tour0:38", "Pricing0:20"]);
    expect(pills.every((pill) => !pill.hidden)).toBe(true);
    const top = (pill: HTMLElement | undefined): number => Number.parseFloat(pill?.style.top ?? "0");
    expect(top(pills[0])).toBeLessThan(top(pills[1]));
    pills[1]?.click();

    expect(picked).toEqual([1]);
    expect(menu.open).toBe(false);
    menu.close();
  });

  it("hides its button during a call, and folds its pills on Escape", () => {
    const menu = aMenu([]);
    menu.offer([{ title: "Site tour", ms: 38_000 }]);
    menu.available(true);
    menu.toggle(true);
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    expect(menu.open).toBe(false);

    menu.available(false);
    expect(document.querySelector<HTMLButtonElement>(".pc-walks")?.hidden).toBe(true);
    menu.close();
  });

  it("offers one walk alone beside the face for a few seconds, and folds it away when the pills fan out", () => {
    vi.useFakeTimers();
    const picked: number[] = [];
    const menu = aMenu(picked);
    menu.offer([{ title: "Site tour", ms: 38_000 }, { title: "Pricing", ms: 20_000 }]);
    menu.available(true);
    const pills = [...document.querySelectorAll<HTMLButtonElement>(".pc-pill")];

    menu.suggest(1);
    vi.advanceTimersByTime(50);
    expect(pills.map((pill) => !pill.hidden)).toEqual([false, true]);
    vi.advanceTimersByTime(OFFERED_MS + 300);
    expect(pills[1]?.hidden).toBe(true);
    menu.suggest(1);
    pills[1]?.click();
    expect(picked).toEqual([1]);
    menu.close();
    vi.useRealTimers();
  });
});
