/** A benchmark's conditions: how one is named on the command, the line it sets, a setup's numbers under each, and what holds under all of them. */

import { describe, expect, it } from "vitest";

import { clearsBoth, flagOf, heldUnderEvery, inputUnder, parseCondition, parsePlayed, requireTold, sayLine, shiftsOf, underEach } from "../../../src/evals/service/conditions.js";
import { setupOf, type BenchCall } from "@pinecall/agents/evals";
import { SimulateInput } from "../../../src/evals/service/simulation.js";

const BARS = { floor: 0.9, ceiling_s: 1.5 };
const QUIET = { lines: 6, unanswered: 0, phantom_turns: 0, cut_by_the_room: 0, cut_by_a_murmur: 0, talked_over: 0, word_error_rate: 0.03 };
const A_ROOM = { lines: 6, unanswered: 1, phantom_turns: 15, cut_by_the_room: 10, cut_by_a_murmur: 0, talked_over: 0, word_error_rate: 0.9 };

const A_CALL: BenchCall = {
  call: "call_1",
  comparison: "cmp_1",
  caller: "books-a-visit",
  setup: "thinks google/gemini-3.5-flash-lite",
  condition: "clean",
  round: 1,
  not_counted: null,
  completed: true,
  reason: null,
  ended: "caller_hung_up",
  started_at: 100,
  length_s: 95,
  reply_s: 1.2,
  replies_s: [1.2],
  slowest_reply_s: 1.2,
  cost_usd: 0.05,
  unpriced: [],
  stages: { llm_ttft: null, tts_ttfb: null, transcription_delay: null, end_of_turn_delay: null },
  judges: [],
  hearing: QUIET,
  recording: null,
  timed: false,
  lines: [],
};
const calls = (each: Partial<BenchCall>[]): BenchCall[] => each.map((one, at) => ({ ...A_CALL, call: `call_${String(at + 1)}`, round: at + 1, ...one }));
const CLEAN = { name: "clean", line: {}, comparisons: ["cmp_1"] };
const A_TELEVISION = { name: "television-20", line: { ambience: "television", "background-noise": 20 }, comparisons: ["cmp_2"] };

describe("a condition on the command", () => {
  it("is a name, and after a colon what the line is under it, in the line's own flags' names", () => {
    expect(parseCondition("television-20:ambience=television,background-noise=20")).toEqual({ name: "television-20", line: { ambience: "television", "background-noise": 20 }, comparisons: [] });
    expect(parseCondition("clean")).toEqual({ name: "clean", line: {}, comparisons: [] });
    expect(parseCondition("bad-line:packet-loss=0.05,delay=200,via=sip").line).toEqual({ "packet-loss": 0.05, delay: 200, via: "sip" });
  });

  it("refuses a knob the line has not, a number that is none, and an ambience that does not say how loud", () => {
    for (const word of ["Television:ambience=street", "tv:volume=3", "tv:background-noise=loud", "tv:ambience=television", "tv:delay=1,delay=2", ":delay=1"]) expect(() => parseCondition(word), word).toThrow();
  });

  it("played before is a name and its comparisons", () => {
    expect(parsePlayed("television-20:cmp_4f1c2a9be07d,cmp_91aa03c7d2e1")).toEqual({ name: "television-20", line: null, comparisons: ["cmp_4f1c2a9be07d", "cmp_91aa03c7d2e1"] });
    for (const word of ["television-20", "television-20:", "tv:call_1"]) expect(() => parsePlayed(word), word).toThrow();
  });

  it("is told from another by its name", () => {
    expect(() => requireTold([CLEAN, A_TELEVISION])).not.toThrow();
    expect(() => requireTold([CLEAN, { ...A_TELEVISION, name: "clean" }])).toThrow("two conditions are named clean");
  });

  it("sets the run's line and nothing else of it, and is refused when the line may not be so", () => {
    const asked = SimulateInput.parse({ persona: "books-a-visit", voice: true, repeats: 3 });
    expect(inputUnder(asked, A_TELEVISION)).toMatchObject({ persona: "books-a-visit", voice: true, repeats: 3, ambience: "television", backgroundNoise: 20 });
    expect(inputUnder(asked, CLEAN)).toEqual(asked);
    expect(() => inputUnder(asked, { name: "tv", line: { ambience: "disco", "background-noise": 20 }, comparisons: [] })).toThrow("--condition tv");
  });

  it("is said in a few words, and as the flag that places it again", () => {
    expect(sayLine(A_TELEVISION.line)).toBe("television 20 dB under the caller");
    expect(sayLine({})).toBe("the line as the callers have it");
    expect(sayLine(null)).toBe("");
    expect(flagOf(A_TELEVISION)).toBe("--condition television-20:ambience=television,background-noise=20");
    expect(flagOf(CLEAN)).toBe("--condition clean");
  });
});

describe("a setup under each condition", () => {
  const all = calls([{}, {}, { condition: "television-20", hearing: A_ROOM, length_s: 540 }, { condition: "television-20", hearing: A_ROOM, length_s: 600, completed: false }]);

  it("has the baseline's numbers as its own, and each condition's beside them, read against the baseline's", () => {
    const { baseline, under } = underEach({ llm: "google/gemini-3.5-flash-lite" }, all, [CLEAN, A_TELEVISION], ["books-a-visit"], BARS);
    expect([baseline.completed.completed, baseline.completed.of]).toEqual([2, 2]);
    expect(under.map((its) => [its.condition, its.completed.completed, its.completed.of, its.moved === null])).toEqual([["clean", 2, 2, true], ["television-20", 1, 2, false]]);
    expect(under[1]?.moved).toMatchObject({ share_change: -0.5, regressed: true });
  });

  it("says what the line moved most, a call, the largest first and two at most", () => {
    const { under } = underEach({}, all, [CLEAN, A_TELEVISION], ["books-a-visit"], BARS);
    expect(under[1]?.moved?.most.map((shift) => [shift.what, shift.was, shift.now])).toEqual([["turns nobody said a call", 0, 15], ["replies the room cut a call", 0, 10]]);
  });

  it("says nothing moved when the line moved nothing by a step", () => {
    const clean = setupOf({}, calls([{}, {}]), ["books-a-visit"], BARS);
    const street = setupOf({}, calls([{ length_s: 100 }, { length_s: 110, hearing: { ...QUIET, word_error_rate: 0.08 } }]), ["books-a-visit"], BARS);
    expect(shiftsOf(street, clean)).toEqual([]);
  });

  it("never lets a word error past one outweigh what the room did to the turns", () => {
    const clean = setupOf({}, calls([{}]), ["books-a-visit"], BARS);
    const slow = setupOf({}, calls([{ reply_s: 7.9, hearing: { ...QUIET, word_error_rate: 19, cut_by_the_room: 20 } }]), ["books-a-visit"], BARS);
    expect(shiftsOf(slow, clean).map((shift) => shift.what)).toEqual(["replies the room cut a call", "seconds to reply"]);
  });
});

describe("holding under every condition", () => {
  it("is clearing both bars under each of them, and a setup that fails one is not named", () => {
    const holds = underEach({ llm: "a/holds" }, calls([{}, { condition: "television-20" }]), [CLEAN, A_TELEVISION], ["books-a-visit"], BARS);
    const falls = underEach({ llm: "a/falls" }, calls([{}, { condition: "television-20", completed: false }]), [CLEAN, A_TELEVISION], ["books-a-visit"], BARS);
    const held = heldUnderEvery([{ ...holds.baseline, under: holds.under }, { ...falls.baseline, under: falls.under }], [CLEAN, A_TELEVISION]);
    expect(held.names).toEqual(["thinks a/holds"]);
    expect(held.says).toBe("under every condition (clean, television-20) thinks a/holds clears both bars");
    expect(heldUnderEvery([{ ...falls.baseline, under: falls.under }], [CLEAN, A_TELEVISION]).says).toBe("under every condition (clean, television-20) none clears both bars");
  });

  it("is never said of a setup most of whose calls were set aside there", () => {
    const refused = { not_counted: { kind: "vendor" as const, why: "openai refused this call's model" }, completed: null, condition: "television-20" };
    const lost = underEach({}, calls([{}, { condition: "television-20" }, refused, refused]), [CLEAN, A_TELEVISION], ["books-a-visit"], BARS);
    expect(lost.under[1]?.thin).toBe(true);
    expect(clearsBoth(lost.under[1]!)).toBe(false);
  });
});
