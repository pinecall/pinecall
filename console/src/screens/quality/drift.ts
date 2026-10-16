/** Each judge's held-rate over two windows of the agent's finished calls, as `pinecall runs drift` counts it — read off the `pinecall start` holding the agent. */

import { useEffect, useState } from "react";
import { z } from "zod";

import type { Credentials } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { dev } from "../../lib/dev";

/** A judge's pass rate in one window. */
const RateSchema = z.object({ held: z.int(), settled: z.int(), percent: z.number() });

/** A judge's rate in both windows and the delta. Null means no verdicts, not zero. */
const JudgeDriftSchema = z.object({
  judge: z.string(),
  before: RateSchema.nullable(),
  now: RateSchema.nullable(),
  delta: z.number().nullable(),
});
export type JudgeDrift = z.infer<typeof JudgeDriftSchema>;

/** A failed verdict with the seqs it cites. */
const BrokeSchema = z.object({
  call: z.string(),
  judge: z.string(),
  seqs: z.array(z.int()),
  reason: z.string(),
});

/** Drift report: per-judge rates, unjudged counts, recent failures, worst drop. */
const DriftedSchema = z.object({
  agent: z.string(),
  window: z.number(),
  baseline: z.number(),
  threshold: z.number(),
  drift: z.object({
    judges: z.array(JudgeDriftSchema),
    notJudged: z.object({ now: z.int(), before: z.int() }),
    broke: z.array(BrokeSchema),
    worst: z.number().nullable(),
  }),
});
export type Drifted = z.infer<typeof DriftedSchema>;

/**
 * Each judge's pass rate over two windows. Computed by the `pinecall start` process (same code as
 * `pinecall runs drift`) to avoid hundreds of round trips from the browser.
 */
export async function readDrift(
  credentials: Credentials,
  agent: string,
  window: number,
  baseline: number,
): Promise<Drifted> {
  return DriftedSchema.parse(await dev(credentials, agent, "drift.read", { agent, window, baseline }));
}

const A_DAY = 24 * 60 * 60;

/** The windows Quality reads, as `pinecall runs drift` does by default: a week against a month. */
export const NOW_DAYS = 7;
export const BEFORE_DAYS = 30;

/**
 * The agent's drift, or null — while asked, and for good when nothing answers: the count is the
 * process's, and a world with no `pinecall start` holding the agent has no such process to ask.
 */
export function useDrift(agent: string): Drifted | null {
  const credentials = useCredentials();
  const [drifted, setDrifted] = useState<Drifted | null>(null);
  useEffect(() => {
    let gone = false;
    setDrifted(null);
    if (agent === "") return;
    readDrift(credentials, agent, NOW_DAYS * A_DAY, BEFORE_DAYS * A_DAY).then(
      (read) => {
        if (!gone) setDrifted(read);
      },
      () => undefined,
    );
    return () => {
      gone = true;
    };
  }, [credentials, agent]);
  return drifted;
}
