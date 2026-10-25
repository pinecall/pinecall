// A section that names a walk gets a small ▶ in its corner, and the site's own button plays one too, for a walk the agent published.

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
    expect([buttons[0]?.style.left, buttons[0]?.style.top]).toEqual(["20px", "120px"]);
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

  it("shows the site's own button for a published walk while it may play, and plays it on a click", () => {
    document.body.innerHTML = `<button data-pinecall-play="overview" hidden><span>▶</span></button><button data-pinecall-play="gone" hidden>▶</button>`;
    const played: string[] = [];
    const corners = new Corners(document, (part) => document.body.append(part), { label: "Play", onPlay: (name) => played.push(name) });
    corners.offer([{ name: "overview", title: "What Pinecall is", ms: 38_000 }]);
    const [own, gone] = [...document.querySelectorAll<HTMLButtonElement>("[data-pinecall-play]")];

    corners.place(true);
    expect([own?.hidden, gone?.hidden]).toEqual([false, true]);
    own?.querySelector("span")?.click();
    expect(played).toEqual(["overview"]);
    corners.place(false);
    expect(own?.hidden).toBe(true);
    own?.click();
    expect(played).toEqual(["overview"]);
    corners.close();
  });
});
