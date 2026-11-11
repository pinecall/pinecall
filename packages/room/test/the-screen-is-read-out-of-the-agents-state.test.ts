// The screen an agent drew is a public field of its state: read whole, and what does not read as a part is left out.

import { describe, expect, it } from "vitest";

import { screenOf } from "../src/index.js";
import { initialState } from "../src/wire/reduce.js";

describe("screenOf", () => {
  it("is empty for a call whose agent drew none", () => {
    expect(screenOf(initialState())).toEqual([]);
  });

  it("reads the parts, their props and what they hold, in order", () => {
    const slot = { part: "slot", props: { time: "09:30" }, children: [] };
    const state = { ...initialState(), app_state: { screen: [{ part: "stage", props: { desk: "front" }, children: [slot, "or later"] }] } };
    expect(screenOf(state)).toEqual([{ part: "stage", props: { desk: "front" }, children: [slot, "or later"] }]);
  });

  it("leaves out what is no part, and gives a part without props or children empty ones", () => {
    const state = { ...initialState(), app_state: { screen: [{ part: "orb" }, 7, null, { props: {} }, "hello"] } };
    expect(screenOf(state)).toEqual([{ part: "orb", props: {}, children: [] }, "hello"]);
  });
});
