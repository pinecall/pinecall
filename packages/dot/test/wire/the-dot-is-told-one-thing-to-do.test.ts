// The dot sends what was typed with the page's named things, and is told one thing to do, checked before it is done.

import { describe, expect, it } from "vitest";

import { decisionOf, namedIn } from "../../src/wire/ask.js";

describe("the page's named things", () => {
  it("are each line with a name and a ref, its role kept, the rest left out", () => {
    const page = ['- region "Pricing" [ref=e9]', '  - heading "Pricing" [level=2] [ref=e10]', '  - text "$39 / month"', '- banner', '  - textbox "Your name" [ref=e41] [empty]'].join("\n");

    expect(namedIn(page)).toEqual([
      { ref: "e9", role: "region", name: "Pricing" },
      { ref: "e10", role: "heading", name: "Pricing" },
      { ref: "e41", role: "textbox", name: "Your name" },
    ]);
  });
});

describe("a decision", () => {
  it("is a walk, a thing by its ref, the agent or nothing, with how sure it is; anything else is none", () => {
    expect(decisionOf({ do: "walk", walk: "plans", confidence: 0.8 })).toEqual({ do: "walk", walk: "plans", confidence: 0.8 });
    expect(decisionOf({ do: "show", target: "e5", confidence: 0.9 })).toEqual({ do: "show", target: "e5", confidence: 0.9 });
    expect(decisionOf({ do: "talk", confidence: 0.7 })).toEqual({ do: "talk", confidence: 0.7 });
    expect(decisionOf({ do: "show", target: "#pricing", confidence: 0.9 })).toBeNull();
    expect(decisionOf({ do: "click", target: "e5", confidence: 0.9 })).toBeNull();
    expect(decisionOf({ do: "none" })).toBeNull();
  });
});
