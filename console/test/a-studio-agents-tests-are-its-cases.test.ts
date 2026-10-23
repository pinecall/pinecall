/** Studio's Test: a run plays the approved cases not held out, and a run's matrix reads as one verdict per case with the judges' reasons. */

import { expect, test } from "vitest";

import type { EvalCase } from "../src/screens/cases/door";
import type { Matrix } from "../src/screens/evals/door";
import { notPlayedBecause, playable, resultsOf, tallyWords } from "../src/screens/studio/testing";

const A_CASE: EvalCase = {
  id: "case_1",
  agent: "front-desk",
  name: "no-dice-un-precio",
  golden: { name: "no-dice-un-precio", turns: [{ say: "¿Cuánto cuesta?" }], expect: { not: ["€"] } },
  source_call: null,
  source_env: "sandbox",
  held_out: false,
  author: "ana@clinica.uy",
  created_at: 1791460000.5,
  status: "approved",
  broke: [],
  source_version: null,
  kept_in_repo: false,
  decided_by: null,
  source: "person",
};

const SCORE = { score: 0, criteria: "", judge_calls: 1 };

test("a run plays the approved cases not held out: a pending one, a dismissed one and a held-out one each say why not", () => {
  const pending = { ...A_CASE, id: "case_2", name: "waits", status: "pending" as const };
  const dismissed = { ...A_CASE, id: "case_3", name: "gone", status: "dismissed" as const };
  const heldOut = { ...A_CASE, id: "case_4", name: "kept-back", held_out: true };
  expect(playable([A_CASE, pending, dismissed, heldOut]).map((kept) => kept.name)).toEqual(["no-dice-un-precio"]);
  expect(notPlayedBecause(A_CASE)).toBeNull();
  expect(notPlayedBecause(pending)).toBe("waiting for a decision");
  expect(notPlayedBecause(dismissed)).toBe("dismissed");
  expect(notPlayedBecause(heldOut)).toBe("held out");
});

test("a matrix is one verdict per case: held when every score passed, broke with each failing reason once, the metric standing in for an empty one", () => {
  const matrix: Matrix = {
    models: ["openai/gpt-5.4-mini", "anthropic/claude-haiku-5.5"],
    goldens: ["no-dice-un-precio", "abre-en-book", "never-played"],
    metrics: ["silence", "grounded"],
    judge_calls: 6,
    runs: [
      { model: "openai/gpt-5.4-mini", golden: "no-dice-un-precio", scores: [{ ...SCORE, metric: "silence", passed: false, reason: "it said “80 euros”" }, { ...SCORE, metric: "grounded", passed: true, reason: "" }], summary: null },
      { model: "anthropic/claude-haiku-5.5", golden: "no-dice-un-precio", scores: [{ ...SCORE, metric: "silence", passed: false, reason: "it said “80 euros”" }, { ...SCORE, metric: "grounded", passed: false, reason: "" }], summary: null },
      { model: "openai/gpt-5.4-mini", golden: "abre-en-book", scores: [{ ...SCORE, metric: "t1.reply", passed: true, reason: "" }], summary: null },
      { model: "anthropic/claude-haiku-5.5", golden: "abre-en-book", scores: [{ ...SCORE, metric: "t1.reply", passed: true, reason: "" }], summary: null },
    ],
    failures: [],
  };
  const results = resultsOf(matrix);
  expect(results).toEqual([
    { name: "no-dice-un-precio", verdict: "broke", reasons: ["it said “80 euros”", "grounded"] },
    { name: "abre-en-book", verdict: "held" },
    { name: "never-played", verdict: "not judged" },
  ]);
  expect(tallyWords(results)).toBe("1 of 2 held");
});

test("a case played under several models holds only when it held under every one", () => {
  const matrix: Matrix = {
    models: ["a", "b"],
    goldens: ["x"],
    metrics: ["says"],
    judge_calls: 2,
    runs: [
      { model: "a", golden: "x", scores: [{ ...SCORE, metric: "says", passed: true, reason: "" }], summary: null },
      { model: "b", golden: "x", scores: [{ ...SCORE, metric: "says", passed: false, reason: "it never said the hours" }], summary: null },
    ],
    failures: [],
  };
  expect(resultsOf(matrix)).toEqual([{ name: "x", verdict: "broke", reasons: ["it never said the hours"] }]);
});
