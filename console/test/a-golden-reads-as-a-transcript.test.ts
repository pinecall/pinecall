/** A golden reads as a transcript: each step a sentence, each `t{n}.*` metric back on its turn and step, the turns after a break not played and the final checks skipped. */

import { expect, test } from "vitest";

import type { Golden } from "@pinecall/core/wire/rest-goldens";
import { brokeAt, finalChecks, metricsOf, readGolden, readScores, stepWords, type Scored } from "../src/screens/evals/golden-words";

// The brief's own golden: a slot found, read back, a fact of the backend, and the booking.
const BOOKS_AFTER_YES: Golden = {
  name: "books-after-yes",
  turns: [
    {
      say: "Anything Tuesday afternoon?",
      then: [{ tool: "find_slots", args: { day: "2026-10-14" }, within_ms: 1500 }, { reply: { says_any: ["16:00"], intent: "offers a slot on Tuesday afternoon" } }],
    },
    { say: "That one works.", then: [{ no_tool: "book" }, { reply: { intent: "reads the slot back and asks for a yes" } }, { nothing_else: true }] },
    { event: { name: "slot_freed", data: { at: "15:30" } } },
    { say: "Yes, confirm it.", then: [{ tool: "book" }, { reply: { says: ["booked"], not: ["free"] } }, { end: "agent" }] },
  ],
  expect: { not: ["guarantee"], grounded: true, register: "usted", judges: ["consent"] },
};

const held = (metric: string): Scored => ({ metric, passed: true, reason: "ok" });
const broke = (metric: string, reason: string): Scored => ({ metric, passed: false, reason });

test("each step is one plain sentence", () => {
  const sentences = (BOOKS_AFTER_YES.turns ?? []).flatMap((turn) => (turn.then ?? []).map(stepWords));
  expect(sentences).toEqual([
    "calls find_slots with day 2026-10-14 · within 1.5 s",
    "replies saying one of “16:00” — and: offers a slot on Tuesday afternoon",
    "never calls book",
    "replies: reads the slot back and asks for a yes",
    "nothing else happens",
    "calls book",
    "replies saying “booked”, never saying “free”",
    "the agent ends the call",
  ]);
});

test("the final checks are said one per metric the runtime scores them under", () => {
  expect(finalChecks(BOOKS_AFTER_YES.expect ?? {})).toEqual([
    { metric: "silence", said: "never says “guarantee”" },
    { metric: "grounded", said: "states no price, hour, date or name the call did not carry" },
    { metric: "register", said: "addresses the caller as usted" },
    { metric: "consent", said: "consent holds when asked again" },
  ]);
});

test("a turn's metrics are named as the runtime names them, a repeat numbered and an event's turn naming none", () => {
  expect(metricsOf({ say: "hi", then: [{ tool: "find_slots" }, { reply: { intent: "greets" } }, { tool: "find_slots" }] }, 2)).toEqual([["t2.tool:find_slots"], ["t2.reply", "t2.intent"], ["t2.tool:find_slots#2"]]);
  expect(metricsOf({ event: { name: "slot_freed" } }, 3)).toEqual([]);
});

test("a golden read with no run has no states", () => {
  const read = readGolden(BOOKS_AFTER_YES);
  expect(read.turns.map((turn) => turn.state)).toEqual([undefined, undefined, undefined, undefined]);
  expect(read.turns[2]?.input).toEqual({ event: "slot_freed", data: { at: "15:30" } });
  expect(read.turns[2]?.lines).toEqual([]);
});

test("the first broken step cuts the golden: its turn broke, the later turns are not played, the final checks skipped", () => {
  const scores = [
    held("t1.tool:find_slots"),
    held("t1.reply"),
    held("t1.intent"),
    held("t2.no_tool:book"),
    held("t2.reply"),
    broke("t2.intent", "the agent booked without reading the slot back"),
    held("t2.nothing_else"),
  ];
  const read = readGolden(BOOKS_AFTER_YES, scores);
  expect(read.turns.map((turn) => turn.state)).toEqual(["held", "broke", "not played", "not played"]);
  expect(read.turns[1]?.lines.map((line) => line.state)).toEqual(["held", "broke", "held"]);
  expect(read.turns[1]?.lines[1]?.why).toBe("the agent booked without reading the slot back");
  expect(read.turns[3]?.lines.every((line) => line.state === undefined)).toBe(true);
  expect(read.finals.map((line) => line.state)).toEqual(["skipped", "skipped", "skipped", "skipped"]);
  expect(brokeAt(read)).toBe("turn 2 · replies: reads the slot back and asks for a yes");
});

test("a golden that held all the way is scored at the end", () => {
  const scores = [
    ...["t1.tool:find_slots", "t1.reply", "t1.intent", "t2.no_tool:book", "t2.reply", "t2.intent", "t2.nothing_else", "t4.tool:book", "t4.reply", "t4.end"].map(held),
    held("silence"),
    held("grounded"),
    broke("register", "turn 6 says tú"),
    held("consent"),
  ];
  const read = readGolden(BOOKS_AFTER_YES, scores);
  expect(read.turns.map((turn) => turn.state)).toEqual(["held", "held", "held", "held"]);
  expect(read.finals.map((line) => line.state)).toEqual(["held", "held", "broke", "held"]);
  expect(brokeAt(read)).toBe("the final checks");
});

test("a run read without its golden still lands each metric on its turn, said in words", () => {
  const read = readScores([held("t1.tool:find_slots"), broke("t1.reply", "never said 16:00"), held("grounded")]);
  expect(read.turns.map((turn) => [turn.number, turn.state, turn.lines.map((line) => line.said)])).toEqual([[1, "broke", ["calls find_slots", "replies"]]]);
  expect(read.finals).toEqual([{ said: "states no price, hour, date or name the call did not carry", state: "skipped" }]);
});
