/** Calls as a terminal reads them: the policy's +1 floor, a narrowed page that goes on, a search's sources by where they came from. */

import { describe, expect, it } from "vitest";

import { chatLine, entryLine, log, policy, sessions } from "../../src/calls/render.js";

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

describe("the sessions", () => {
  const one = { call: "call_7211bd743634463eb744fc9c89a89c3e", channel: "web", direction: "inbound", started_at: 100, ended_at: 103.1, end_reason: "caller_hung_up", cost: { usd: 0.0015 }, outcome: "Hello Ana! For Tuesday, I have 9:00 and 10:30 available." };

  it("says a written conversation waiting for its contact is open, and only a call with somebody on it live", () => {
    const waiting = { ...one, channel: "email", status: "active", live: false, ended_at: null, end_reason: null };
    const [, , written, spoken] = sessions({ agent: "front-desk", calls: [waiting, { ...waiting, channel: "phone", live: true }] as never });
    expect(written).toContain(" open ");
    expect(written).not.toContain("live");
    expect(spoken).toContain(" live ");
  });

  it("cuts a row at the terminal's width, so no row wraps and pushes the header away; a pipe gets it whole", () => {
    const whole = sessions({ agent: "front-desk", calls: [one] as never });
    expect(whole[2]).toBe("call_7211bd743634463eb744fc9c89a89c3e  web inbound  3.1s    caller hung up  $0.0015  Hello Ana! For Tuesday, I have 9:00 and 10:30 available.");
    const narrow = sessions({ agent: "front-desk", calls: [one] as never }, 100);
    expect(narrow[2]).toBe("call_7211bd743634463eb744fc9c89a89c3e  web inbound  3.1s    caller hung up  $0.0015  Hello Ana! For…");
    expect(narrow[2]).toHaveLength(100);
    // The title and the next step are sentences, left as they are.
    expect([narrow[0], narrow.at(-1)]).toEqual([whole[0], whole.at(-1)]);
  });
});

describe("a chat's line for an error", () => {
  it("says the reason, its first line, and leaves the vendor's own account to the log read whole", () => {
    const message = "anthropic refused this call's model: Your credit balance is too low.\ntype='llm_error' label='livekit.plugins.anthropic.llm.LLM' error=APIStatusError(…)";
    const line = chatLine({ seq: 4, type: "error", call: "call_1", data: { code: "component_dead_end", message, recoverable: false } });
    expect(line).toBe("✗ anthropic refused this call's model: Your credit balance is too low.");
  });
});
