/** A benchmark's numbers: a share with its interval, what does not count left out of all of them, rounds, the verdict, a regression. */

import { describe, expect, it } from "vitest";

import { movedSince, percentile, setupOf, shareOf, verdictOf, type BenchCall, type Setup } from "../../src/evals/scorecard.js";

const BARS = { floor: 0.9, ceiling_s: 1.5 };

const A_CALL: BenchCall = {
  call: "call_1",
  comparison: "cmp_1",
  caller: "books-a-visit",
  setup: "thinks google/gemini-3.5-flash-lite",
  round: 1,
  not_counted: null,
  completed: true,
  reason: null,
  ended: "caller_hung_up",
  started_at: 100,
  length_s: 90,
  reply_s: 1.2,
  replies_s: [1.1, 1.2, 1.3],
  slowest_reply_s: 1.3,
  cost_usd: 0.05,
  unpriced: [],
  stages: { llm_ttft: 0.5, tts_ttfb: 0.14, transcription_delay: null, end_of_turn_delay: null },
  judges: [{ name: "expected-outcome", verdict: "held", reason: "" }],
  hearing: { lines: 6, unanswered: 0, phantom_turns: 0, cut_by_the_room: 0, cut_by_a_murmur: 0, talked_over: 1, word_error_rate: 0.02 },
  recording: "calls/call_1.ogg",
  timed: false,
  lines: [],
};

const calls = (each: Partial<BenchCall>[]): BenchCall[] => each.map((one, at) => ({ ...A_CALL, call: `call_${String(at + 1)}`, ...one }));

describe("a share of calls", () => {
  it("comes with Wilson's interval at 95%: 19 of 20 plausibly sits between 76% and 99%", () => {
    const share = shareOf(19, 20);
    expect(share.share).toBe(0.95);
    expect(Math.round((share.low ?? 0) * 100)).toBe(76);
    expect(Math.round((share.high ?? 0) * 100)).toBe(99);
  });

  it("of every call is still not a certainty: 14 of 14 has a floor of 78%", () => {
    expect(Math.round((shareOf(14, 14).low ?? 0) * 100)).toBe(78);
  });

  it("of no calls is no share", () => {
    expect(shareOf(0, 0)).toEqual({ completed: 0, of: 0, share: null, low: null, high: null });
  });
});

describe("the value a share of the measures sits under", () => {
  it("is the middle of them at a half, between two of them when it falls there", () => {
    expect(percentile([3, 1, 2], 0.5)).toBe(2);
    expect(percentile([1, 2, 3, 4], 0.5)).toBe(2.5);
    expect(percentile([], 0.5)).toBeNull();
  });
});

describe("one setup's numbers", () => {
  it("leave a call that does not count out of every one of them", () => {
    const setup = setupOf({ llm: "google/gemini-3.5-flash-lite" }, calls([{}, { completed: false, reply_s: 1.4, cost_usd: 0.07 }, { not_counted: { kind: "vendor", why: "openai refused this call's model" }, completed: null, reply_s: 12.9, cost_usd: 0.3 }]), ["books-a-visit"], BARS);
    expect([setup.calls, setup.not_counted]).toEqual([2, 1]);
    expect([setup.completed.completed, setup.completed.of]).toEqual([1, 2]);
    expect(setup.reply.p50).toBeCloseTo(1.3);
    expect(setup.cost.total).toBeCloseTo(0.12);
    expect(setup.cost.per_completed).toBeCloseTo(0.12);
  });

  it("count each round apart, and say how far one round moved from another", () => {
    const setup = setupOf({}, calls([{ round: 1 }, { round: 1, caller: "hurried" }, { round: 2, completed: false }, { round: 2, caller: "hurried" }]), ["books-a-visit", "hurried"], BARS);
    expect(setup.rounds).toEqual([{ round: 1, completed: 2, of: 2 }, { round: 2, completed: 1, of: 2 }]);
    expect(setup.spread).toEqual({ least: 0.5, most: 1 });
    expect(setup.by_caller.map((one) => [one.caller, one.completed, one.of, one.every])).toEqual([["books-a-visit", 1, 2, false], ["hurried", 2, 2, true]]);
    expect(setup.kind).toBe("own settings");
  });

  it("hold the setup to the floor and to the ceiling, each by itself", () => {
    const slow = setupOf({ llm: "anthropic/claude-haiku-5-5" }, calls([{ reply_s: 2.1 }, { reply_s: 2.3 }]), ["books-a-visit"], BARS);
    expect(slow.clears).toEqual({ floor: true, ceiling: false });
    const unjudged = setupOf({}, calls([{ completed: null }]), ["books-a-visit"], BARS);
    expect(unjudged.clears.floor).toBeNull();
  });

  it("sum how the setup heard its callers, and count each judge's answers", () => {
    const setup = setupOf({}, calls([{}, { judges: [{ name: "expected-outcome", verdict: "broken", reason: "moved it to Tuesday" }], hearing: { lines: 4, unanswered: 1, phantom_turns: 2, cut_by_the_room: 0, cut_by_a_murmur: 0, talked_over: 0, word_error_rate: 0.06 } }]), ["books-a-visit"], BARS);
    expect(setup.hearing).toMatchObject({ calls: 2, lines: 10, unanswered: 1, phantom_turns: 2, talked_over: 1 });
    expect(setup.hearing?.word_error_rate).toBeCloseTo(0.04);
    expect(setup.judges).toEqual([{ name: "expected-outcome", held: 1, broken: 1, other: 0 }]);
  });
});

describe("the verdict", () => {
  const fast = (): Setup => setupOf({ realtime: "google/gemini-3.8-live" }, calls([{ reply_s: 0.7, cost_usd: 0.04 }, { reply_s: 0.8, cost_usd: 0.04 }]), ["books-a-visit"], BARS);
  const dear = (): Setup => setupOf({ realtime: "xai/grok-voice-3.0" }, calls([{ reply_s: 0.5, cost_usd: 0.14 }, { reply_s: 0.5, cost_usd: 0.14 }]), ["books-a-visit"], BARS);
  const slow = (): Setup => setupOf({ llm: "anthropic/claude-haiku-5-5" }, calls([{ reply_s: 2.1, cost_usd: 0.02 }, { reply_s: 2.2, cost_usd: 0.02 }]), ["books-a-visit"], BARS);

  it("takes the cheapest per completed call of the setups that clear both bars, never a cheaper one that missed one", () => {
    const verdict = verdictOf([dear(), fast(), slow()], BARS);
    expect(verdict.passed).toBe(true);
    expect(verdict.cleared).toEqual(["talks xai/grok-voice-3.0", "talks google/gemini-3.8-live"]);
    expect(verdict.winner).toBe("talks google/gemini-3.8-live");
  });

  it("never calls cheapest a setup with a model nobody priced", () => {
    const unpriced = setupOf({ realtime: "xai/grok-voice-3.0" }, calls([{ reply_s: 0.5, cost_usd: 0, unpriced: ["grok-voice-3.0"] }]), ["books-a-visit"], BARS);
    expect(verdictOf([unpriced, dear()], BARS).winner).toBe("talks xai/grok-voice-3.0");
    expect(verdictOf([unpriced, fast()], BARS).winner).toBe("talks google/gemini-3.8-live");
  });

  it("holds to no bar a setup that lost most of its calls, however well the few left went", () => {
    const refused = { not_counted: { kind: "vendor" as const, why: "xai refused this call" }, completed: null };
    const lost = setupOf({ realtime: "xai/grok-voice-3.0" }, calls([{ reply_s: 0.5 }, refused, refused]), ["books-a-visit"], BARS);
    expect([lost.thin, lost.calls, lost.not_counted]).toEqual([true, 1, 2]);
    const verdict = verdictOf([lost, fast()], BARS);
    expect(verdict.cleared).toEqual(["talks google/gemini-3.8-live"]);
    expect(verdict.says).toContain("talks xai/grok-voice-3.0 lost most of its calls and is held to no bar");
    expect(verdictOf([lost], BARS).passed).toBe(false);
  });

  it("fails when no setup clears both, and is no verdict when nobody judged a call", () => {
    expect(verdictOf([slow()], BARS)).toMatchObject({ passed: false, winner: null });
    expect(verdictOf([setupOf({}, calls([{ completed: null }]), ["books-a-visit"], BARS)], BARS).passed).toBeNull();
  });
});

describe("a setup against an earlier report of it", () => {
  const now = (done: boolean[]): Setup => setupOf({}, calls(done.map((completed, at) => ({ completed, round: at + 1 }))), ["books-a-visit"], BARS);
  const was = { name: "the agent's own settings", completed: { share: 1 }, reply: { p50: 1.2 }, cost: { per_completed: 0.05 } };

  it("regressed when its share fell by more than the earlier report's own rounds moved among themselves", () => {
    expect(movedSince(now([true, false, false, true]), { ...was, spread: { least: 0.75, most: 1 } })).toMatchObject({ share_change: -0.5, regressed: true });
    expect(movedSince(now([true, true, true, false]), { ...was, spread: { least: 0.75, most: 1 } }).regressed).toBe(false);
  });

  it("did not regress when it held or rose", () => {
    expect(movedSince(now([true, true]), { ...was, spread: null }).regressed).toBe(false);
  });
});
