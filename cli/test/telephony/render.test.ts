/** What a line of `numbers available` says of a number: routed here, held by another org, or free to import. */

import { describe, expect, it } from "vitest";

import { ownedLine } from "../../src/telephony/render.js";

describe("an owned number's line", () => {
  it("says what another org holds, so nobody tries to import it", () => {
    const one = { number: "+34910000001", name: "Centralita", account: "AC1", imported: false, held_elsewhere: true };
    expect(ownedLine(one)).toBe("+34910000001 · Centralita · AC1 · held by another org");
  });

  it("says routed here before anything else, and free when nobody routes it", () => {
    const routed = { number: "+34910000002", name: "+34910000002", account: "AC1", imported: true, held_elsewhere: false };
    const free = { ...routed, imported: false };
    expect(ownedLine(routed)).toBe("+34910000002 · AC1 · routed here");
    expect(ownedLine(free)).toBe("+34910000002 · AC1 · not routed here");
  });
});
