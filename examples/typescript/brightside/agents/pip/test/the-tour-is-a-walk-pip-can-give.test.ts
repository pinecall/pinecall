// Pip loads with its three walks checked, offers them in its view once the page is seen, and has the pointer's tools.

import { runHook, toolsOf } from "@pinecall/agents";
import { describe, expect, it } from "vitest";

import Pip from "../agent.js";

describe("Pip", () => {
  it("carries the tour, five sentences, each with its moves", () => {
    const tour = Pip.macros["tour"];

    expect(tour?.steps).toHaveLength(5);
    expect(tour?.steps.every((step) => step.beats.length > 0)).toBe(true);
  });

  it("carries the plans and the first visit too, each a walk with a title for its button", () => {
    expect(Object.keys(Pip.macros)).toEqual(["tour", "plans", "visit"]);
    expect(Object.values(Pip.macros).map((walk) => walk.title)).toEqual(["Site tour", "Plans and prices", "Your first visit"]);
  });

  it("offers the tour in its view once the visitor's page has been seen", async () => {
    const pip = new Pip();
    await runHook(pip, "onEvent", "page.seen", { text: '- link "Services" [ref=e2]', why: "call" }, { source: "participant", seq: 1 });

    expect(pip.seeing()).toContain("- tour: when the visitor asks to be shown around");
  });

  it("can point, highlight, scroll, show where, go home and give a walk, and never leave the page", () => {
    expect(toolsOf(new Pip()).map((one) => one.name).sort()).toEqual(["explain", "fill", "here", "highlight", "home", "point", "runMacro", "scrollTo", "unhighlight"]);
  });
});
