// A section names its walk, and the one across the screen's middle is the visitor's; the site's own button plays one. Only for a walk the agent published.

import { afterEach, describe, expect, it } from "vitest";

import { Sections } from "../../src/pointer/sections.js";

afterEach(() => {
  document.body.innerHTML = "";
});

function aSection(walk: string, top: number): { at: (top: number) => void } {
  const section = document.createElement("section");
  section.setAttribute("data-pinecall-walk", walk);
  document.body.append(section);
  const at = (value: number): void => {
    section.getBoundingClientRect = () => new DOMRect(0, value, 1200, 600);
  };
  at(top);
  return { at };
}

describe("the section the visitor is on", () => {
  it("is the one across the screen's middle, with the name of its published walk", () => {
    const hero = aSection("overview", -200);
    const studio = aSection("studio", 700);
    const sections = new Sections(document, { onPlay: () => undefined });
    sections.offer(["overview", "studio"]);

    expect(sections.current()).toBe("overview");
    hero.at(-900);
    studio.at(100);
    expect(sections.current()).toBe("studio");
    studio.at(-900);
    expect(sections.current()).toBeNull();
    sections.close();
  });

  it("names none for a walk the agent did not publish", () => {
    aSection("unknown", 100);
    const sections = new Sections(document, { onPlay: () => undefined });
    sections.offer(["studio"]);

    expect(sections.current()).toBeNull();
    sections.close();
  });
});

describe("the site's own button", () => {
  it("shows for a published walk while it may play, and plays it on a click", () => {
    document.body.innerHTML = `<button data-pinecall-play="overview" hidden><span>▶</span></button><button data-pinecall-play="gone" hidden>▶</button>`;
    const played: string[] = [];
    const sections = new Sections(document, { onPlay: (name) => played.push(name) });
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
