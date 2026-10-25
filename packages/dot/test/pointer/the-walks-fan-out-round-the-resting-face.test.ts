// The walks fan out from a small button beside the resting face, in an arc toward the page, and a pick plays one.

import { afterEach, describe, expect, it } from "vitest";

import { Menu, PAGE, STEP, fanned } from "../../src/pointer/menu.js";

afterEach(() => {
  document.body.innerHTML = "";
  document.head.innerHTML = "";
});

function aMenu(picked: number[], current: () => number = () => -1): Menu {
  return new Menu(document, (part) => document.body.append(part), {
    dock: "right",
    label: "Walks",
    more: "More walks",
    face: () => ({ at: { x: 900, y: 700 }, radius: 36 }),
    onPick: (index) => picked.push(index),
    current,
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

  it("shows a page of walks at a time, and the button under them turns to the next page, then back to the first", () => {
    const menu = aMenu([]);
    const titles = ["One", "Two", "Three", "Four", "Five", "Six"];
    menu.offer(titles.map((title) => ({ title, ms: 10_000 })));
    menu.available(true);
    const shown = (): string[] => [...document.querySelectorAll<HTMLButtonElement>(".pc-pill")].filter((pill) => !pill.hidden).map((pill) => (pill.textContent ?? "").replace(/0:10$/, ""));
    const more = document.querySelector<HTMLButtonElement>(".pc-more");

    document.querySelector<HTMLButtonElement>(".pc-walks")?.click();
    expect(shown()).toEqual(titles.slice(0, PAGE));
    expect(more?.hidden).toBe(false);
    more?.click();
    expect(shown()).toEqual(titles.slice(PAGE));
    expect(more?.classList.contains("pc-last")).toBe(true);
    more?.click();
    expect(shown()).toEqual(titles.slice(0, PAGE));
    menu.toggle(false);
    expect([shown(), more?.hidden]).toEqual([[], true]);
    menu.close();
  });

  it("marks the walk of the section the visitor is on, and opens on the page it stands on", () => {
    const titles = ["One", "Two", "Three", "Four", "Five", "Six"];
    const menu = aMenu([], () => 5);
    menu.offer(titles.map((title) => ({ title, ms: 10_000 })));
    menu.available(true);
    const pills = [...document.querySelectorAll<HTMLButtonElement>(".pc-pill")];

    document.querySelector<HTMLButtonElement>(".pc-walks")?.click();

    expect(pills.filter((pill) => !pill.hidden).map((pill) => pill.textContent?.replace(/0:10$/, ""))).toEqual(titles.slice(PAGE));
    expect(pills.map((pill) => pill.classList.contains("pc-here"))).toEqual([false, false, false, false, false, true]);
    menu.close();
  });

  it("marks none when the visitor is on no section with a walk, and opens on the first page", () => {
    const menu = aMenu([], () => -1);
    menu.offer([{ title: "One", ms: 10_000 }, { title: "Two", ms: 10_000 }]);
    menu.available(true);

    document.querySelector<HTMLButtonElement>(".pc-walks")?.click();

    expect(document.querySelectorAll(".pc-here")).toHaveLength(0);
    menu.close();
  });

  it("follows the page while it is open: the mark moves to the walk of the section scrolled into, and its page shows", () => {
    let here = 0;
    const menu = aMenu([], () => here);
    const titles = ["One", "Two", "Three", "Four", "Five", "Six"];
    menu.offer(titles.map((title) => ({ title, ms: 10_000 })));
    menu.available(true);
    const pills = [...document.querySelectorAll<HTMLButtonElement>(".pc-pill")];
    const marked = (): number => pills.findIndex((pill) => pill.classList.contains("pc-here"));
    const shown = (): number[] => pills.flatMap((pill, at) => (pill.hidden ? [] : [at]));
    document.querySelector<HTMLButtonElement>(".pc-walks")?.click();
    expect([marked(), shown()]).toEqual([0, [0, 1, 2, 3]]);

    here = 2;
    window.dispatchEvent(new Event("scroll"));
    expect([marked(), shown()]).toEqual([2, [0, 1, 2, 3]]);
    here = 5;
    window.dispatchEvent(new Event("scroll"));
    expect([marked(), shown()]).toEqual([5, [4, 5]]);
    // The visitor pages back by hand within the same section: a scroll there does not pull them away.
    document.querySelector<HTMLButtonElement>(".pc-more")?.click();
    window.dispatchEvent(new Event("scroll"));
    expect(shown()).toEqual([0, 1, 2, 3]);
    here = -1;
    window.dispatchEvent(new Event("scroll"));
    expect([marked(), shown()]).toEqual([-1, [0, 1, 2, 3]]);
    menu.close();
  });
});
