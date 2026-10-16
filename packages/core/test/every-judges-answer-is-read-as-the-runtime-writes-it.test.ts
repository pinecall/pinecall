/** Every judge asks a model: a score carries N/A, a classification, the evals it bills and whose key it ran on, as the runtime writes them. */

import { expect, test } from "vitest";

import { CallScoreSchema, CallSummarySchema } from "../src/wire/events-call.js";
import { JudgeListSchema, JudgeTriedSchema } from "../src/wire/rest-evals.js";

const EVIDENCE = { seqs: [12], said: "Le confirmo el jueves." };

test("a score of a verdict, an N/A and a classification reads each answer and the evals billed", () => {
  const read = CallScoreSchema.parse({
    passed: true,
    judges: [
      { name: "grounded", verdict: "held", criteria: "…", reason: "every fact is in the tools", evidence: EVIDENCE },
      { name: "consent", verdict: "na", criteria: "…", reason: "no irreversible tool ran", evidence: { seqs: [] } },
      { name: "sentiment", verdict: "classified", criteria: "…", reason: "thanked the agent", evidence: EVIDENCE, choice: "positive" },
      { name: "politeness", verdict: "classified", criteria: "…", reason: "warm throughout", evidence: EVIDENCE, score: 4 },
    ],
    judge_calls: 4,
    evals: 3,
    own_key: true,
  });
  expect(read.judges.map((judge) => judge.verdict)).toEqual(["held", "na", "classified", "classified"]);
  expect([read.judges[2]?.choice, read.judges[3]?.score]).toEqual(["positive", 4]);
  expect([read.evals, read.own_key]).toEqual([3, true]);
});

test("a summary a simulated caller played says so", () => {
  const read = CallSummarySchema.parse({
    reason: "caller_hung_up",
    outcome: "booked",
    duration_s: 40,
    turns: 6,
    usage: [],
    cost: { usd: 0, rows: [], unpriced: [] },
    simulated: true,
  });
  expect(read.simulated).toBe(true);
});

test("a list of judges is the library's switched, then the org's own, each with how it answers", () => {
  const read = JudgeListSchema.parse({
    judges: [
      { name: "consent", owner: "pinecall", on: true, question: "…", answer: "verdict", choices: [], when: "always", trigger: "", reads: ["facts"], summary: "…", version: 1, why: "…", recommended: true },
      { name: "mood", owner: "org", on: true, question: "…", answer: "choice", choices: ["calm", "upset"], when: "trigger", trigger: "The caller complained.", reads: [], recommended: false, author: "m_ana", set_at: 1790000000.1 },
    ],
  });
  expect(read.judges.map((judge) => [judge.owner, judge.answer, judge.when])).toEqual([
    ["pinecall", "verdict", "always"],
    ["org", "choice", "trigger"],
  ]);
  expect(() => JudgeListSchema.parse({ judges: [{ name: "x", question: "q", runs_on: "every-call", author: "a", set_at: 1 }] })).toThrow();
});

test("a try answers each call's judgment, or why there was none, with the evals it spent", () => {
  const read = JudgeTriedSchema.parse({
    rows: [
      { call: "call_a", judgment: { name: "mood", verdict: "classified", criteria: "…", reason: "…", evidence: EVIDENCE, choice: "calm" } },
      { call: "call_b", judgment: null, not_judged: "the call has not finished" },
    ],
    evals: 1,
    cost_usd: 0.0004,
  });
  expect(read.rows.map((row) => row.judgment?.choice ?? row.not_judged)).toEqual(["calm", "the call has not finished"]);
});
