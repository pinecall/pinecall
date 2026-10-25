// The face fills its host with one SVG, drawn at once, its body in the shape and colour asked and nothing outside it, and takes it away when closed; a page with no Web Audio still gets a face.

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
    // The body, the mouth, and the two clips: the mouth's and the body's own.
    const paths = [...(svg?.querySelectorAll("path") ?? [])];
    expect(paths).toHaveLength(4);
    for (const path of paths) expect(path.getAttribute("d")).toMatch(/^M .* Z$/);
    drawn.close();
  });

  it("draws nothing outside its body: no halo, the sheen clipped to it, the box not overflowed", () => {
    const host = document.createElement("div");
    const drawn = face(host, aRoom(), { shape: "blob", color: "#7a4cd6" });
    const svg = host.querySelector("svg");

    expect(svg?.getAttribute("overflow")).toBeNull();
    const wide = [...(svg?.querySelectorAll("circle") ?? [])].filter((circle) => Number(circle.getAttribute("r")) > 5);
    expect(wide.length).toBeGreaterThan(0);
    expect(wide.every((circle) => circle.getAttribute("clip-path")?.startsWith("url(#"))).toBe(true);
    expect((host as HTMLElement).style.getPropertyValue("--pc-face")).toBe("#7a4cd6");
    drawn.reshape("squircle");
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
