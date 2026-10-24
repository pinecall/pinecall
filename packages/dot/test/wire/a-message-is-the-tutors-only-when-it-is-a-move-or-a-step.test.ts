// What arrives on pinecall.ui is the tutor's only as a cursor move, a macro step or the agent asking for the page; a macro file is checked when the class loads.

import { describe, expect, it } from "vitest";

import { linesOf, macroOf, tutoring } from "../../src/wire/index.js";

describe("a message on pinecall.ui", () => {
  it("is a cursor move with its action and its target, a ref or a name", () => {
    expect(tutoring({ type: "cursor", action: "point", target: "e12" })).toEqual({ type: "cursor", action: "point", target: "e12" });
    expect(tutoring({ type: "cursor", action: "scroll_to", target: "Questions" })).toEqual({ type: "cursor", action: "scroll_to", target: "Questions" });
  });

  it("is a move typing the visitor's words into a field, which names the field and the words", () => {
    expect(tutoring({ type: "cursor", action: "type", target: "Your name", text: "Jordan Lee" })).toEqual({ type: "cursor", action: "type", target: "Your name", text: "Jordan Lee" });
    expect(tutoring({ type: "cursor", action: "type", target: "Your name" })).toBeNull();
    expect(tutoring({ type: "cursor", action: "type", text: "Jordan Lee" })).toBeNull();
  });

  it("is a macro step with its sentence and beats", () => {
    const step = { type: "macro.step", macro: "tour", step: 0, say: "Pricing is simple.", beats: [{ word: "Pricing", do: "scroll_to", find: ["region", "Pricing"] }] };

    expect(tutoring(step)).toEqual(step);
  });

  it("is the agent asking for the page", () => {
    expect(tutoring({ type: "look" })).toEqual({ type: "look" });
  });

  it("is not the tutor's when it is a card, choices, a click, or anything malformed", () => {
    expect(tutoring({ type: "html", html: "<p>hi</p>" })).toBeNull();
    expect(tutoring({ type: "cursor", action: "click", target: "e1" })).toBeNull();
    expect(tutoring({ type: "macro.step", macro: "tour", step: 0, say: "Hi", beats: [{ word: "Hi" }] })).toBeNull();
    expect(tutoring("point e12")).toBeNull();
    expect(tutoring({ type: "macro.step", macro: "tour", step: 0, say: "Hi", beats: [{ word: "Hi", do: "type" }] })).toBeNull();
  });
});

describe("the lines a page sends", () => {
  it("are each a ref, its words and its move, and anything else is left out", () => {
    const lines = linesOf([
      { at: "e20", say: "Pricing is simple.", do: "highlight" },
      { at: "Pricing", say: "Not a ref.", do: "point" },
      { at: "e21", say: " ", do: "point" },
      { at: "e22", say: "Fill me.", do: "type" },
      "e23",
    ]);

    expect(lines).toEqual([{ at: "e20", say: "Pricing is simple.", do: "highlight" }]);
    expect(linesOf(undefined)).toEqual([]);
  });
});

describe("a macro file", () => {
  it("is taken with its steps, its name and when to run it", () => {
    const macro = macroOf("tour", { when: "the visitor asks to be shown around", steps: [{ say: "Up here are our services.", beats: [{ word: "services.", do: "point", find: ["link", "Services"] }] }] });

    expect(macro.name).toBe("tour");
    expect(macro.when).toBe("the visitor asks to be shown around");
    expect(macro.steps).toHaveLength(1);
  });

  it("is refused naming the word a beat hangs on that its sentence never says", () => {
    expect(() => macroOf("tour", { steps: [{ say: "Up here are our services.", beats: [{ word: "Pricing", do: "point" }] }] })).toThrow(
      'macro tour: step 1 never says "Pricing"',
    );
  });

  it("is refused with no steps, or a step that says nothing", () => {
    expect(() => macroOf("tour", { steps: [] })).toThrow("macro tour: no steps");
    expect(() => macroOf("tour", { steps: [{ say: " ", beats: [] }] })).toThrow("macro tour: step 1 says nothing");
  });
});
