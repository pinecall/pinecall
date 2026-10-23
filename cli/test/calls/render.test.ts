/** Calls as a terminal reads them: the policy's +1 floor said when the setting is wider than it, a narrowed page that goes on. */

import { describe, expect, it } from "vitest";

import { log, policy } from "../../src/calls/render.js";

const row = (calling_hours: { from: number; until: number } | null, per_number_day: number | null) => ({
  policy: { retention_days: null, calling_hours, per_number_day, consent_everywhere: false, disclosure: null, recording_notice: true },
  set_by: null,
  set_at: null,
});

describe("the policy", () => {
  it("says the +1 floor whenever the org's setting is wider than it, and not when it is within", () => {
    const wide = policy(row({ from: 6, until: 23 }, 10) as never);
    expect(wide[1]).toBe("calling hours:  a number is rung from 6:00 to 23:00 of its own day (a +1 number: 8-21)");
    expect(wide[2]).toBe("per number:     one number is rung at most 10 time(s) a day (a +1 number: 3)");
    const within = policy(row({ from: 9, until: 20 }, 2) as never);
    expect(within[1]).toBe("calling hours:  a number is rung from 9:00 to 20:00 of its own day");
    expect(within[2]).toBe("per number:     one number is rung at most 2 time(s) a day");
    expect(policy(row(null, null) as never).slice(1, 3)).toEqual(["calling hours:  a number is rung at any hour of its day (a +1 number: 8-21)", "per number:     no limit of calls to one number a day (a +1 number: 3)"]);
  });
});

describe("a log page", () => {
  it("narrowed to nothing but with more after it says the log goes on; at its end, that nothing is kept", () => {
    const more = log({ call: "call_1", entries: [], next: 41, live: true } as never, 0);
    expect(more[0]).toBe("call_1 · nothing of these types in this page, after seq 0; the log goes on");
    expect(more.at(-1)).toBe("more: pinecall sessions log call_1 --after 41");
    expect(log({ call: "call_1", entries: [], next: null, live: false } as never, 40)).toEqual(["call_1 · nothing kept after seq 40"]);
  });
});
