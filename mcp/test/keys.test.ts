/** A key is proven at the gateway once and remembered: a good one for a minute, a bad one for half of it, a failure never. */

import { describe, expect, it } from "vitest";

import { BAD_FOR_MS, GOOD_FOR_MS, Keys, MOST_REMEMBERED, fingerprint } from "../src/keys.js";

/** A gateway that takes the keys named, and counts what it was asked. */
function gateway(good: readonly string[]): { asked: string[]; prove: (key: string) => Promise<unknown> } {
  const asked: string[] = [];
  return { asked, prove: async (key) => (asked.push(key), good.includes(key) ? { org: "org_1" } : null) };
}

describe("the keys", () => {
  it("ask the gateway once for a key, good or bad, until what is remembered of it runs out", async () => {
    let now = 0;
    const { asked, prove } = gateway(["good"]);
    const keys = new Keys(prove, () => now);
    expect([await keys.opens("good"), await keys.opens("good"), await keys.opens("bad"), await keys.opens("bad")]).toEqual([true, true, false, false]);
    expect(asked).toEqual(["good", "bad"]);
    now = BAD_FOR_MS;
    await keys.opens("good");
    await keys.opens("bad");
    expect(asked).toEqual(["good", "bad", "bad"]);
    now = GOOD_FOR_MS;
    await keys.opens("good");
    expect(asked).toEqual(["good", "bad", "bad", "good"]);
  });

  it("remember nothing of a gateway that did not answer", async () => {
    let down = true;
    const keys = new Keys(async () => {
      if (down) throw new Error("the gateway is away");
      return { org: "org_1" };
    });
    await expect(keys.opens("good")).rejects.toThrow(/away/);
    down = false;
    expect(await keys.opens("good")).toBe(true);
  });

  it("forget the oldest once they remember too many", async () => {
    const { asked, prove } = gateway([]);
    const keys = new Keys(prove, () => 0);
    for (let at = 0; at <= MOST_REMEMBERED; at += 1) await keys.opens(`made-up-${at}`);
    await keys.opens("made-up-0");
    await keys.opens(`made-up-${MOST_REMEMBERED}`);
    expect(asked.length).toBe(MOST_REMEMBERED + 2);
    expect(asked.at(-1)).toBe("made-up-0");
  });

  it("are remembered by their fingerprint, never themselves", () => {
    expect(fingerprint("pk_secret")).toMatch(/^[0-9a-f]{64}$/);
    expect(fingerprint("pk_secret")).not.toContain("pk_secret");
  });
});
