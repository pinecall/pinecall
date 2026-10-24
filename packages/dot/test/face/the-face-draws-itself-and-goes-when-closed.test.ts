// The face fills its host with one SVG, drawn at once, and takes it away when closed; a page with no Web Audio still gets a face.

import { describe, expect, it } from "vitest";

import { face } from "../../src/face/index.js";
import { aRoom } from "../a-room.js";

describe("a face on the page", () => {
  it("draws itself into its host at once, mouth and all", () => {
    const host = document.createElement("div");
    const drawn = face(host, aRoom());

    const svg = host.querySelector("svg");
    expect(svg).not.toBeNull();
    expect(svg?.querySelectorAll("ellipse").length).toBeGreaterThanOrEqual(2);
    const paths = [...(svg?.querySelectorAll("path") ?? [])];
    expect(paths).toHaveLength(2);
    for (const path of paths) expect(path.getAttribute("d")).toMatch(/^M /);
    drawn.close();
  });

  it("wakes without Web Audio, and leaves its host empty when closed, twice or not", () => {
    const host = document.createElement("div");
    const drawn = face(host, aRoom());
    drawn.wake();
    drawn.close();
    drawn.close();

    expect(host.children).toHaveLength(0);
  });

  it("gives two faces on one page clips of their own", () => {
    const one = document.createElement("div");
    const two = document.createElement("div");
    const first = face(one, aRoom());
    const second = face(two, aRoom());

    expect(one.querySelector("clipPath")?.id).not.toBe(two.querySelector("clipPath")?.id);
    first.close();
    second.close();
  });
});
