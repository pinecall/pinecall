// A number of the box says how it came and what a call to it does now: no call opens until the
// operator approves it, nobody runs the agent, or it is picked up; a search finds it by digits, org or agent.

import { describe, expect, it } from "vitest";

import { cameIn, matching, whenItRings } from "../src/screens/box/box-numbers.js";
import { type BoxNumber } from "../src/screens/box/door-floor.js";

const row = (changes: Partial<BoxNumber> = {}): BoxNumber => ({
  number: "+59829001199",
  channel: "phone",
  org: "clinica",
  env: "production",
  agent: "recepcion",
  came_in: "twilio",
  running: true,
  via: null,
  approved: true,
  ...changes,
});

describe("a number of the box", () => {
  it("is picked up only once approved and while a process runs the agent", () => {
    expect(whenItRings(row()).text).toBe("picked up");
    expect(whenItRings(row({ running: false })).tone).toBe("amber");
    expect(whenItRings(row({ approved: false })).text).toBe("waits for your approval");
  });

  it("says how it came, and a way the runtime adds later as the runtime names it", () => {
    expect(cameIn(row())).toBe("its Twilio");
    expect(cameIn(row({ came_in: "ported" }))).toBe("ported");
  });

  it("is found by its digits however they are typed, or by its org or agent", () => {
    const rows = [row(), row({ number: "+14155550142", org: "otra", agent: "ventas" })];
    expect(matching(rows, "2900 1199").map((one) => one.org)).toEqual(["clinica"]);
    expect(matching(rows, "VENTAS").map((one) => one.org)).toEqual(["otra"]);
    expect(matching(rows, " ")).toHaveLength(2);
  });
});

