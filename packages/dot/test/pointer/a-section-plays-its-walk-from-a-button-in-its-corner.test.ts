// A section that names a walk gets a small ▶ in its corner, for a walk the agent published, and a click plays it.

import { afterEach, describe, expect, it } from "vitest";

import { Corners } from "../../src/pointer/corners.js";

afterEach(() => {
  document.body.innerHTML = "";
  document.head.innerHTML = "";
});

function aSection(walk: string, top: number): HTMLElement {
  const section = document.createElement("section");
  section.setAttribute("data-pinecall-walk", walk);
  section.getBoundingClientRect = () => new DOMRect(0, top, 1200, 600);
  document.body.append(section);
  return section;
}

describe("a section's corner button", () => {
  it("stands in the corner of a section naming a published walk, plays it, and none for a walk not published", () => {
    aSection("studio", 100);
    aSection("unknown", 100);
    const played: string[] = [];
    const corners = new Corners(document, (part) => document.body.append(part), { label: "Play", onPlay: (name) => played.push(name) });
    corners.offer([{ name: "studio", title: "The Studio", ms: 30_000 }]);

    corners.place(true);
    const buttons = [...document.querySelectorAll<HTMLButtonElement>(".pc-corner")];
    expect(buttons).toHaveLength(1);
    expect(buttons[0]?.hidden).toBe(false);
    expect(buttons[0]?.getAttribute("aria-label")).toBe("Play: The Studio (0:30)");
    expect(buttons[0]?.style.top).toBe("120px");
    buttons[0]?.click();

    expect(played).toEqual(["studio"]);
    corners.close();
  });

  it("hides while a call is on or a walk plays, and while its corner is off the screen", () => {
    const section = aSection("studio", 100);
    const corners = new Corners(document, (part) => document.body.append(part), { label: "Play", onPlay: () => undefined });
    corners.offer([{ name: "studio", title: "The Studio", ms: 30_000 }]);
    const button = (): HTMLButtonElement | null => document.querySelector(".pc-corner");

    corners.place(false);
    expect(button()?.hidden).toBe(true);
    section.getBoundingClientRect = () => new DOMRect(0, -300, 1200, 600);
    corners.place(true);
    expect(button()?.hidden).toBe(true);
    section.remove();
    corners.place(true);
    expect(button()).toBeNull();
    corners.close();
  });
});
