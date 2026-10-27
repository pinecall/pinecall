// A page read aloud with its top scrolled away starts from the first part still in view: what was scrolled past is not read again.

import { afterEach, describe, expect, it } from "vitest";

import { fromHere, readingOf } from "../../src/tutor/reading.js";

afterEach(() => {
  document.body.innerHTML = "";
});

const rect = (top: number, height: number): DOMRect =>
  ({ left: 0, top, width: 600, height, right: 600, bottom: top + height, x: 0, y: top, toJSON: () => ({}) }) as DOMRect;

describe("a page read from where it is", () => {
  it("starts at the first part not above the screen, and whole when that is the first", () => {
    document.body.innerHTML = `<main data-pinecall-read><p id="a">Uno.</p><p id="b">Dos.</p><p id="c">Tres.</p></main>`;
    const at = (id: string): HTMLElement => document.getElementById(id)!;
    at("a").getBoundingClientRect = () => rect(-80, 40);
    at("b").getBoundingClientRect = () => rect(-30, 40);
    at("c").getBoundingClientRect = () => rect(20, 40);

    const here = fromHere(readingOf(document, "Leer")!);

    expect(here.walk.steps.map((step) => ("say" in step ? step.say : "?"))).toEqual(["Dos.", "Tres."]);
    expect(here.at.map((element) => element.id)).toEqual(["b", "c"]);

    at("a").getBoundingClientRect = () => rect(10, 40);
    expect(fromHere(readingOf(document, "Leer")!).walk.steps).toHaveLength(3);
  });
});
