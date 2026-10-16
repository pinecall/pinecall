/** Compare an eval run with the previous one: judgments that broke and that recovered. */

import type { EvalRun, Matrix } from "./door";

// Judgments are keyed by (golden, model, metric) and listed by name, never averaged.
const APART = " · ";

export interface Delta {
  broke: string[];
  recovered: string[];
}

export interface Tally {
  held: number;
  judgments: number;
}

function judgmentOf(model: string, golden: string, metric: string): string {
  return [golden, model, metric].join(APART);
}

/** Count held judgments in a run; zero when there is no matrix. */
export function tallyOf(matrix: Matrix | null): Tally {
  if (matrix === null) {
    return { held: 0, judgments: 0 };
  }
  const judgments = matrix.runs.flatMap((cell) => cell.scores);
  return { held: judgments.filter((score) => score.passed).length, judgments: judgments.length };
}

/**
 * Changes from `before` to `run`, or null with no earlier run. Only judgments present in both are
 * compared, so a new golden is never reported as a regression.
 */
export function deltaBetween(run: EvalRun, before: EvalRun | undefined): Delta | null {
  if (before?.matrix == null || run.matrix === null) {
    return null;
  }
  const then = heldBy(before.matrix);
  const now = heldBy(run.matrix);
  const both = [...now.keys()].filter((judgment) => then.has(judgment));
  return {
    broke: both.filter((judgment) => then.get(judgment) === true && now.get(judgment) === false),
    recovered: both.filter((judgment) => then.get(judgment) === false && now.get(judgment) === true),
  };
}

function heldBy(matrix: Matrix): Map<string, boolean> {
  const held = new Map<string, boolean>();
  for (const cell of matrix.runs) {
    for (const score of cell.scores) {
      held.set(judgmentOf(cell.model, cell.golden, score.metric), score.passed);
    }
  }
  return held;
}
