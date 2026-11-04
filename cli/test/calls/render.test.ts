/** Calls as a terminal reads them: the policy's +1 floor, a narrowed page that goes on, a search's sources by where they came from. */

import { describe, expect, it } from "vitest";

import { entryLine, log, policy } from "../../src/calls/render.js";

const row = (calling_hours: { from: number; until: number } | null, per_number_day: number | null) => ({
  policy: { retention_days: null, calling_hours, per_number_day, consent_everywhere: false, disclosure: null, recording_notice: true },
  set_by: null,
  set_at: null,
});

describe("the policy", () => {
  it("says the +1 floor whenever the org's setting is wider than it, and not when it is within", () => {
    const wide = policy(row({ from: 6, until: 23 }, 10) as never);
    expect(wide[1]).toBe("calling hours:  a number is rung from 6:00 to 23:00 of its own day (a +1 number: 8-21)");
    expect(wide[2]).toBe("per number:     one number is rung at most 10 times a day (a +1 number: 3)");
    const within = policy(row({ from: 9, until: 20 }, 2) as never);
    expect(within[1]).toBe("calling hours:  a number is rung from 9:00 to 20:00 of its own day");
    expect(within[2]).toBe("per number:     one number is rung at most 2 times a day");
    expect(policy(row(null, null) as never).slice(1, 3)).toEqual(["calling hours:  a number is rung at any hour of its day (a +1 number: 8-21)", "per number:     no limit of calls to one number a day (a +1 number: 3)"]);
  });
});

describe("a log page", () => {
  it("narrowed to nothing but with more after it says the log goes on; at its end, that nothing is kept", () => {
    const more = log({ call: "call_1", entries: [], next: 41, live: true } as never, 0);
    expect(more[0]).toBe("call_1 · nothing of these types in this page, after seq 0; the log goes on");
    expect(more.at(-1)).toBe("  → pinecall sessions log call_1 --after 41 reads on");
    expect(log({ call: "call_1", entries: [], next: null, live: false } as never, 40)).toEqual(["call_1 · nothing kept after seq 40"]);
  });
});

describe("a search's sources", () => {
  it("are named by base, path and heading with their score, not cut inside the first excerpt", () => {
    const data = {
      query: "do you open on saturdays",
      took_ms: 31,
      sources: [
        { id: "c1", base: "library-d", path: "hours.md", heading: "Saturdays", score: 0.91, excerpt: "We open on Saturdays from 9:00 to 13:30. ".repeat(10) },
        { id: "c2", base: "library-d", path: "prices.md", heading: null, score: 0.42, excerpt: "A check-up is 60 EUR." },
      ],
    };
    const line = entryLine({ seq: 7, ts: 1_792_000_000, call: "call_1", agent: "a", type: "docs.sources", ephemeral: false, data } as never);
    expect(line).toContain('"do you open on saturdays" → library-d/hours.md › Saturdays 0.91 · library-d/prices.md 0.42');
  });
});

describe("a log page read whole", () => {
  it("leaves the machinery's quiet entries out, says how many, and --verbose shows them", () => {
    const page = {
      call: "call_1",
      entries: [
        { seq: 8, ts: 1_792_150_442.31, type: "turn.user", data: { text: "hola" } },
        { seq: 9, ts: 1_792_150_442.32, type: "agent.state", data: { state: "thinking" } },
        { seq: 10, ts: 1_792_150_442.4, type: "state.changed", data: { state: { message: { name: "Ana", about: "a delivery" } }, changed: ["message"], cause: { tool: "takeMessage" } } },
      ],
      next: null,
      live: false,
    };
    const lines = log(page as never, 0);
    expect(lines[0]).toBe("call_1 · 2 entries, 1 quiet left out");
    // A state is said in words, never as its JSON.
    expect(lines[2]).toMatch(/state\.changed {2}takeMessage set message\.name Ana · message\.about a delivery$/);
    expect(lines.at(-1)).toBe("  → --verbose shows every entry");
    expect(log(page as never, 0, true)[0]).toBe("call_1 · 3 entries");
  });
});
