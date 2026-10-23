/** A Studio agent's tests are its cases: which of them a run plays, and what a run's matrix says of each. */

import type { EvalCase } from "../cases";
import type { Matrix } from "../evals";

/** The cases a run plays: the approved ones not held out — the very ones the nightly plays. */
export function playable(cases: readonly EvalCase[]): EvalCase[] {
  return cases.filter((kept) => notPlayedBecause(kept) === null);
}

/** Why a case is not played, in a few words, or null when it is. */
export function notPlayedBecause(kept: EvalCase): string | null {
  if (kept.status === "pending") return "waiting for a decision";
  if (kept.status === "dismissed") return "dismissed";
  if (kept.held_out) return "held out";
  return null;
}

/** One case after a run: held, broke with each judge's reason, or never judged (the run gave it no cell). */
export type CaseResult = { name: string; verdict: "held" } | { name: string; verdict: "broke"; reasons: string[] } | { name: string; verdict: "not judged" };

/**
 * Each case the matrix names, in its order. A case played under several models holds only when it
 * held under every one; the reasons are the failing scores' own, each once, the metric's name
 * standing in for a reason left empty.
 */
export function resultsOf(matrix: Matrix): CaseResult[] {
  const names = [...new Set([...matrix.goldens, ...matrix.runs.map((cell) => cell.golden)])];
  return names.map((name): CaseResult => {
    const cells = matrix.runs.filter((cell) => cell.golden === name);
    if (cells.length === 0) return { name, verdict: "not judged" };
    const reasons = [...new Set(cells.flatMap((cell) => cell.scores.filter((score) => !score.passed).map((score) => (score.reason === "" ? score.metric : score.reason))))];
    return reasons.length === 0 ? { name, verdict: "held" } : { name, verdict: "broke", reasons };
  });
}

/** The run in one line: how many of the cases judged held. */
export function tallyWords(results: readonly CaseResult[]): string {
  const judged = results.filter((result) => result.verdict !== "not judged");
  const held = judged.filter((result) => result.verdict === "held").length;
  return `${String(held)} of ${String(judged.length)} held`;
}
