// A walk the agent published is taken by the page only whole: each step with its audio, its timed words and its beats.

import { describe, expect, it } from "vitest";

import { clock, macroOf, onPage, shownOf, tutoring, walksDocument, walksOf } from "../../src/wire/index.js";

const STEP = {
  say: "Up here are our services.",
  audio: "https://gw/v1/lines/9f2c.mp3",
  durationMs: 1610,
  words: [{ text: "Up", startMs: 325, endMs: 495 }],
  beats: [{ word: "Up", do: "point", find: ["link", "Services"] }],
};

describe("the walks a page reads", () => {
  it("are each a name, a title and steps it can play", () => {
    expect(walksOf({ walks: [{ name: "tour", title: "Site tour", when: "asked", steps: [STEP] }] })).toEqual([
      { name: "tour", title: "Site tour", when: "asked", steps: [STEP] },
    ]);
  });

  it("leave out a walk with a step that is not one: no audio, an audio that is no URL, a beat that types", () => {
    const broken = [{ ...STEP, audio: undefined }, { ...STEP, audio: "javascript:alert(1)" }, { ...STEP, beats: [{ word: "Up", do: "type" }] }];

    for (const step of broken) expect(walksOf({ walks: [{ name: "tour", title: "Site tour", steps: [step] }] })).toEqual([]);
    expect(walksOf(null)).toEqual([]);
    expect(walksOf({ walks: "tour" })).toEqual([]);
  });
});

describe("a macro file", () => {
  it("keeps the title its button shows, and none when it gives none", () => {
    const steps = [{ say: "Hi.", beats: [] }];

    expect(macroOf("tour", { title: "Site tour", steps }).title).toBe("Site tour");
    expect(macroOf("tour", { steps }).title).toBeUndefined();
  });
});

describe("the code a step shows", () => {
  const CODE = { title: "agent.ts", text: "export class Desk {}" };

  it("is a window with a title and its text, closed with null, and lines lit from 1, in order", () => {
    expect(shownOf({ code: CODE, lines: [1, 3] })).toEqual({ code: CODE, lines: [1, 3] });
    expect(shownOf({ code: null })).toEqual({ code: null });
    expect(shownOf({})).toEqual({});
    for (const wrong of [{ code: { title: "x" } }, { code: "x" }, { lines: [3, 1] }, { lines: [0, 2] }, { lines: [1.5, 2] }, { lines: [1] }]) {
      expect(shownOf(wrong), JSON.stringify(wrong)).toBeNull();
    }
  });

  it("rides a macro file's step, a published walk's and a step sent in a call, and a macro's end is said", () => {
    const steps = [{ say: "This is the class.", beats: [], code: CODE, lines: [1, 1] }];

    expect(macroOf("code", { steps }).steps[0]).toEqual({ say: "This is the class.", beats: [], code: CODE, lines: [1, 1] });
    expect(() => macroOf("code", { steps: [{ say: "Hi.", beats: [], lines: [2, 1] }] })).toThrow("shows code that is not");
    expect(walksOf({ walks: [{ name: "w", title: "W", steps: [{ ...STEP, code: CODE, lines: [1, 1] }] }] })[0]?.steps[0]).toMatchObject({ code: CODE });
    expect(tutoring({ type: "macro.step", macro: "w", step: 0, say: "Hi.", beats: [], code: CODE })).toMatchObject({ code: CODE });
    expect(tutoring({ type: "macro.done", macro: "w" })).toEqual({ type: "macro.done", macro: "w" });
  });
});

describe("a length", () => {
  it("reads as a clock does", () => {
    expect(clock(38_400)).toBe("0:38");
    expect(clock(61_000)).toBe("1:01");
  });
});

describe("the pages a walk is for", () => {
  it("are paths a macro file names, and a walk keeps them", () => {
    const steps = [{ say: "Hi.", beats: [] }];

    expect(macroOf("keys", { pages: ["/security"], steps }).pages).toEqual(["/security"]);
    expect(macroOf("tour", { steps }).pages).toBeUndefined();
    expect(() => macroOf("keys", { pages: ["security"], steps })).toThrow("begin with a slash");
    expect(() => macroOf("keys", { pages: "/security", steps })).toThrow("begin with a slash");
    expect(walksOf({ walks: [{ name: "keys", title: "Keys", pages: ["/security"], steps: [STEP] }] })[0]?.pages).toEqual(["/security"]);
    expect(walksOf({ walks: [{ name: "keys", title: "Keys", pages: [3], steps: [STEP] }] })[0]?.pages).toBeUndefined();
  });

  it("decide a walk is for the page at a path: any page when it names none, and a trailing slash is the same page", () => {
    expect(onPage(undefined, "/security")).toBe(true);
    expect(onPage([], "/security")).toBe(true);
    expect(onPage(["/security"], "/security/")).toBe(true);
    expect(onPage(["/security/"], "/security")).toBe(true);
    expect(onPage(["/"], "/")).toBe(true);
    expect(onPage(["/"], "/security")).toBe(false);
    expect(onPage(["/security", "/compliance"], "/compliance")).toBe(true);
    // A page that never said its path is any page: nothing is hidden from it.
    expect(onPage(["/security"], "")).toBe(true);
  });
});

describe("the document a page's walks are published under", () => {
  it("is `walks` for the home, and `walks-<page>` for any other, a name a document may have", () => {
    expect(walksDocument("/")).toBe("walks");
    expect(walksDocument("")).toBe("walks");
    expect(walksDocument("/security")).toBe("walks-security");
    expect(walksDocument("/security/")).toBe("walks-security");
    expect(walksDocument("/Developers/SDK")).toBe("walks-developers-sdk");
    const long = walksDocument(`/${"a".repeat(80)}`);
    expect(long).toMatch(/^[a-z][a-z0-9-]{0,39}$/);
  });
});
