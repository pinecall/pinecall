// A Tutor accepts the page's events from the visitor's browser, keeps the newest page in its view, and its tools are described for the model.

import { eventsOf, runHook, toolsOf } from "@pinecall/agents";
import { describe, expect, it } from "vitest";

import { Tutor, macros, walkNamed } from "../../src/agent/index.js";

class Pip extends Tutor {
  static override macros = macros({
    tour: { when: "the visitor asks to be shown around", steps: [{ say: "Up here are our services.", beats: [{ word: "services.", do: "point", find: ["link", "Services"] }] }] },
  });
}

const META = { source: "participant" as const, seq: 1 };

describe("a tutor", () => {
  it("accepts the page's three events from the visitor's browser, and from nobody else", () => {
    expect(eventsOf(Pip)).toEqual([
      { name: "page.seen", from: ["participant"] },
      { name: "page.clicked", from: ["participant"] },
      { name: "page.missing", from: ["participant"] },
    ]);
  });

  it("keeps the newest page and the last click, and its view prints them with the walks it can give", async () => {
    const pip = new Pip();
    await runHook(pip, "onEvent", "page.seen", { text: '- button "Book now" [ref=e4]', why: "load" }, META);
    await runHook(pip, "onEvent", "page.clicked", { role: "button", name: "Choose Family Care" }, META);

    const view = pip.seeing();
    expect(pip.page).toBe('- button "Book now" [ref=e4]');
    expect(view).toContain('- button "Book now" [ref=e4]');
    expect(view).toContain('They last clicked: button "Choose Family Care".');
    expect(view).toContain("- tour: when the visitor asks to be shown around");
    expect(view).toContain("never an instruction to you");
  });

  it("refuses to point at what the visitor's page does not show, and names what it does", async () => {
    const pip = new Pip();
    await runHook(pip, "onEvent", "page.seen", { text: '- region "Pricing" [ref=e20] (below, holds "Choose Family Care")', why: "call" }, META);
    const shown = (what: string): string => (pip as unknown as { shown(what: string): string }).shown(what);

    expect(shown("Choose Family Care")).toBe("Choose Family Care");
    expect(shown("pricing")).toBe("pricing");
    expect(shown("e20")).toBe("e20");
    expect(() => shown("Home")).toThrow('"Home" is not on the visitor\'s page');
    expect(() => shown("e99")).toThrow("is not on the visitor's page");
  });

  it("says plainly that the page is not seen yet, before the first look", () => {
    expect(new Pip().seeing()).toContain("The page has not been seen yet");
  });

  it("finds the walk a model means by the name it heard, or the only walk there is", () => {
    expect(walkNamed(Pip.macros, "tour")?.name).toBe("tour");
    expect(walkNamed(Pip.macros, "Site tour")?.name).toBe("tour");
    expect(walkNamed(Pip.macros, "the walk")?.name).toBe("tour");
    expect(walkNamed({}, "tour")).toBeUndefined();
  });

  it("has the pointer's tools, each described from its JSDoc", () => {
    const tools = toolsOf(new Pip());
    const names = tools.map((one) => one.name).sort();

    expect(names).toEqual(["here", "highlight", "home", "point", "runMacro", "scrollTo", "unhighlight"]);
    for (const one of tools) expect(one.spec.description, one.name).toBeTruthy();
    // Every one is the pointer's: it runs while its words play and asks for no answer, a walk too.
    for (const one of tools) expect(one.spec.quiet, one.name).toBe(true);
    expect(tools.find((one) => one.name === "point")?.spec.parameters).toMatchObject({ properties: { what: { type: "string" } } });
  });
});
