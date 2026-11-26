/** `report.json`: a benchmark as a file, every number of its page and every call under them. One shape, whoever writes it: the CLI's folder, the console's download. */

import type { Bars, BenchCall, Setup, Verdict } from "./scorecard.js";

/** The report's shape: a reader of `report.json` checks it. 2 added conditions (2026-11-26); a baseline may be a report of either. */
export const VERSION = 2;

/** A simulated caller as the report presents it; its behaviour as the gateway says it. */
export interface Caller {
  name: string;
  about: string;
  goal: string;
  expects: string[];
  behavior: object | null;
}

/** `report.json`: every number of the page, and every call under them. */
export interface Benchmark {
  version: typeof VERSION;
  made_at: string;
  agent: string;
  gateway: { url: string; env: string; version: string | null };
  comparisons: string[];
  /** The conditions the calls were placed under, the baseline first; none when the benchmark is of one line. */
  conditions: { name: string; line: Record<string, string | number> | null; says: string; comparisons: string[]; calls: number; counted: number }[];
  spoken: boolean;
  /** The command that places the same calls again, or reads them again. */
  command: string;
  bars: Bars;
  verdict: Verdict;
  callers: Caller[];
  /** Best first: the share completed, then the reply. */
  setups: Setup[];
  /** What the gateway never placed, in its words. */
  refused: { caller: string; setup: string; why: string; condition?: string }[];
  /** Calls still on the line when the report was made: in none of its numbers. */
  on_the_line: number;
  /** The earlier report the setups are held against, when one was given. */
  baseline: { made_at: string; comparisons: string[] } | null;
  calls: BenchCall[];
}
