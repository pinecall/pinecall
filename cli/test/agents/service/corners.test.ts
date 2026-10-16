/** The three corners: which one a key writes, which it reads, the version a write is guarded by, and what a terminal calls it. */

import { describe, expect, it } from "vitest";

import { cornerName, cornerRead, holdsACorner, rowToStartFrom, versionGuarded } from "../../../src/agents/service/corners.js";
import { GatewayClient } from "../../../src/api/client.js";

const person = new GatewayClient("https://gateway.test", "pc_live_person", "sandbox");
const server = new GatewayClient("https://gateway.test", "pc_test_server", "sandbox");
const inProduction = new GatewayClient("https://gateway.test", "pc_live_person", "production");

describe("the corners", () => {
  it("only a person's key in the sandbox holds a corner of its own", () => {
    expect([holdsACorner(person), holdsACorner(server), holdsACorner(inProduction)]).toEqual([true, false, false]);
  });

  it("a key reads its own corner, else the team's; --team starts from the team's", () => {
    expect(cornerRead({ yours: "mine", team: "team" })).toBe("mine");
    expect(cornerRead({ yours: null, team: "team" })).toBe("team");
    expect(rowToStartFrom({ yours: "mine", team: "team" }, true)).toBe("team");
  });

  it("a write is guarded by the corner it lands on, 0 when that corner is empty", () => {
    const answer = { yours: null, team: { version: 3 } };
    expect(versionGuarded(answer, false, person)).toBe(0);
    expect(versionGuarded(answer, false, server)).toBe(3);
    expect(versionGuarded(answer, true, person)).toBe(3);
  });

  it("names the corner written for a terminal", () => {
    expect(cornerName({ world: "sandbox" }, false, person)).toBe("your corner");
    expect(cornerName({ world: "sandbox" }, false, server)).toBe("the team's corner");
    expect(cornerName({ world: "production" }, false, inProduction)).toBe("production");
  });
});
