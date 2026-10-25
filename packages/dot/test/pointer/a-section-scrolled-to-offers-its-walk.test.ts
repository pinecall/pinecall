// The section scrolled to offers its walk, once as it is reached, and the site's own button plays one, for a walk the agent published.

import { afterEach, describe, expect, it } from "vitest";

import { Sections } from "../../src/pointer/sections.js";

afterEach(() => {
  document.body.innerHTML = "";
});

function aSection(walk: string): { section: HTMLElement; at: (top: number) => void } {
  const section = document.createElement("section");
  section.setAttribute("data-pinecall-walk", walk);
  document.body.append(section);
  const at = (top: number): void => {
    section.getBoundingClientRect = () => new DOMRect(0, top, 1200, 600);
  };
  at(2000);
  return { section, at };
}

describe("the section scrolled to", () => {
  it("offers its walk once as it crosses the screen's middle, again when reached anew, and none for a walk not published", () => {
    const studio = aSection("studio");
    const unknown = aSection("unknown");
    const reached: string[] = [];
    const sections = new Sections(document, { onReach: (name) => reached.push(name), onPlay: () => undefined });
    sections.offer(["studio"]);

    sections.place(true);
    studio.at(100);
    sections.place(true);
    sections.place(true);
    expect(reached).toEqual(["studio"]);
    studio.at(-1000);
    unknown.at(100);
    sections.place(true);
    expect(reached).toEqual(["studio"]);
    unknown.at(2000);
    studio.at(100);
    sections.place(true);
    expect(reached).toEqual(["studio", "studio"]);
    sections.close();
  });

  it("offers nothing while a call is on or a walk plays", () => {
    const studio = aSection("studio");
    const reached: string[] = [];
    const sections = new Sections(document, { onReach: (name) => reached.push(name), onPlay: () => undefined });
    sections.offer(["studio"]);

    studio.at(100);
    sections.place(false);

    expect(reached).toEqual([]);
    sections.close();
  });
});

describe("the site's own button", () => {
  it("shows for a published walk while it may play, and plays it on a click", () => {
    document.body.innerHTML = `<button data-pinecall-play="overview" hidden><span>▶</span></button><button data-pinecall-play="gone" hidden>▶</button>`;
    const played: string[] = [];
    const sections = new Sections(document, { onReach: () => undefined, onPlay: (name) => played.push(name) });
    sections.offer(["overview"]);
    const [own, gone] = [...document.querySelectorAll<HTMLButtonElement>("[data-pinecall-play]")];

    sections.place(true);
    expect([own?.hidden, gone?.hidden]).toEqual([false, true]);
    own?.querySelector("span")?.click();
    expect(played).toEqual(["overview"]);
    sections.place(false);
    expect(own?.hidden).toBe(true);
    own?.click();
    expect(played).toEqual(["overview"]);
    sections.close();
  });
});
