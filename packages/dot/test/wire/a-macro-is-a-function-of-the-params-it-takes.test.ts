// A macro is a function: the params it takes fill the slots of its sentences and of what it types, its acts fill, press, wait and read, and a slot nothing fills leaves its step out.

import { describe, expect, it } from "vitest";

import { filled, macroOf, slotsOf, taken, tutoring, valuesFor, walksOf } from "../../src/wire/index.js";

const FIND = {
  params: { treatment: { about: "what they want done" }, plan: { about: "the plan", one_of: { family: "Family Care", essential: "Essential" } } },
  steps: [
    { fill: "Treatment", with: "{treatment}" },
    { press: "Search times" },
    { wait: "Open times", ms: 5000 },
    { read: "Open times", as: "hit", row: "best" },
    { say: "The soonest is {hit.Day} at {hit.Time}.", beats: [{ word: "soonest", do: "highlight", find: ["row", "{hit}"] }], if: "hit" },
    { say: "I found no times for {treatment}.", beats: [], unless: "hit" },
  ],
};

describe("a macro that takes params", () => {
  it("is checked at the class's load: its params, its acts, and each slot a param or a row read before it", () => {
    const macro = macroOf("find", FIND);
    expect(macro.params).toEqual({ treatment: { about: "what they want done" }, plan: { about: "the plan", oneOf: { family: "Family Care", essential: "Essential" } } });
    expect(macro.steps.slice(0, 4)).toEqual([{ fill: "Treatment", with: "{treatment}" }, { press: "Search times" }, { wait: "Open times", ms: 5000 }, { read: "Open times", as: "hit", row: "best" }]);
    expect(macro.steps[4]).toMatchObject({ if: "hit" });

    expect(() => macroOf("x", { steps: [{ say: "Hi {name}.", beats: [] }] })).toThrow("fills {name}, which is no param and no row read before it");
    expect(() => macroOf("x", { steps: [{ say: "At {hit.Time}.", beats: [] }, { read: "Open times", as: "hit" }] })).toThrow("{hit.Time}");
    expect(() => macroOf("x", { params: { who: { about: "x" } }, steps: [{ press: "{who}" }] })).toThrow("is not {fill, with}");
    expect(() => macroOf("x", { steps: [{ wait: "Results", ms: 60_000 }] })).toThrow("is not {fill, with}");
    expect(() => macroOf("x", { params: { who: {} }, steps: [{ say: "Hi.", beats: [] }] })).toThrow("params are");
  });

  it("is called with the visitor's words, cut to a line, and a list's value only among its options", () => {
    const params = macroOf("find", FIND).params ?? {};
    expect(valuesFor(params, { treatment: "  a  cleaning\n", plan: "family", other: "x" })).toEqual({ values: { treatment: "a cleaning", plan: "family" }, wrong: [] });
    expect(valuesFor(params, { plan: "gold" }).wrong).toEqual(["plan is one of family, essential"]);
  });
});

describe("a slot", () => {
  it("is filled from the values, and a text with one nothing filled is none", () => {
    expect(slotsOf("At {hit.Day}, {hit.Time} for {name}.")).toEqual(["hit.Day", "hit.Time", "name"]);
    expect(filled("Thanks, {name}.", { name: "Jordan" })).toBe("Thanks, Jordan.");
    expect(filled("Thanks, {name}.", {})).toBeNull();
    expect(taken({ if: "hit" }, {})).toBe(false);
    expect(taken({ unless: "hit" }, {})).toBe(true);
    expect(taken({ unless: "hit" }, { hit: "Tue · 9:00" })).toBe(false);
  });
});

describe("a walk that takes params, published", () => {
  it("rides its acts and its sentences with slots, to be recorded live; a step that is neither leaves the walk out", () => {
    const steps = [{ fill: "Treatment", with: "{treatment}" }, { say: "Looking for {treatment}.", beats: [], live: true }];
    const [walk] = walksOf({ walks: [{ name: "find", title: "Find a time", params: { treatment: { about: "what" } }, steps }] });
    expect(walk?.params).toEqual({ treatment: { about: "what" } });
    expect(walk?.steps).toEqual(steps);
    expect(walksOf({ walks: [{ name: "find", title: "F", steps: [{ say: "No audio." , beats: [] }] }] })).toEqual([]);
  });

  it("presses and waits in a call only on a target, a wait for its time", () => {
    expect(tutoring({ type: "cursor", action: "press", target: "Search times" })).toEqual({ type: "cursor", action: "press", target: "Search times", text: undefined });
    expect(tutoring({ type: "cursor", action: "wait", target: "Open times", ms: 5000 })).toMatchObject({ action: "wait", ms: 5000 });
    expect(tutoring({ type: "cursor", action: "press" })).toBeNull();
    expect(macroOf.bind(null, "x", { steps: [{ say: "Press it.", beats: [{ word: "Press", do: "press" }] }] })).toThrow("has a beat that is not");
  });
});
