/** Every agent's newest finished suite — how many goldens held and which broke — read once for a screen that is not Test. */

import { useEffect, useState } from "react";

import { useCredentials } from "@pinecall/core/credentials";
import { readEveryRun, type EvalRun } from "./door";

/** An agent's newest suite that finished with a matrix: when, how many cells held, and the goldens that did not. */
export interface Suite {
  agent: string;
  at: number;
  held: number;
  cells: number;
  failing: string[];
}

/** The newest finished suite of each agent, out of every run of the world, newest first. */
export function suitesOf(runs: readonly EvalRun[]): Map<string, Suite> {
  const found = new Map<string, Suite>();
  for (const run of runs) {
    if (found.has(run.agent) || run.status !== "done" || run.matrix === null) continue;
    found.set(run.agent, {
      agent: run.agent,
      at: run.started_at,
      cells: run.matrix.runs.length,
      held: run.matrix.runs.filter((cell) => cell.scores.every((score) => score.passed)).length,
      failing: [...new Set(run.matrix.failures.map((failure) => failure.golden))],
    });
  }
  return found;
}

/** Each agent's newest suite, by slug; empty while asked, and empty for a key the door refuses — no suite is said, not a failure. */
export function useSuites(): Map<string, Suite> {
  const credentials = useCredentials();
  const [suites, setSuites] = useState<Map<string, Suite>>(new Map());
  useEffect(() => {
    let gone = false;
    readEveryRun(credentials).then(
      (runs) => {
        if (!gone) setSuites(suitesOf(runs));
      },
      () => undefined,
    );
    return () => {
      gone = true;
    };
  }, [credentials]);
  return suites;
}
