/** Comparisons read as one benchmark: their rows as calls, each setup's numbers and the verdict against the bars. */

import { callOf, numberRounds, type Read, type Row } from "./calls.js";
import { byStanding, nameOf, setupOf, verdictOf, type AgentValues, type Bars, type BenchCall, type Setup, type Verdict } from "./scorecard.js";

/** A comparison as a benchmark reads it: its id, the callers it rang and a row a call. */
export interface Table<R extends Row = Row> {
  comparison: string;
  persona: string;
  personas: readonly string[];
  rows: readonly R[];
}

/** A benchmark's numbers: every call, each setup best first, and the verdict. */
export interface Standings {
  calls: BenchCall[];
  setups: Setup[];
  verdict: Verdict;
}

/** The rows of the comparisons named, each call once, with the comparison that placed it. */
export function rowsOf<R extends Row>(tables: readonly Table<R>[]): (R & { comparison: string })[] {
  const rows = new Map<string, R & { comparison: string }>();
  for (const table of tables) for (const row of table.rows) if (!rows.has(row.call)) rows.set(row.call, { ...row, comparison: table.comparison });
  return [...rows.values()];
}

/** The rows a benchmark counts or names: those whose call is over, or never began. */
export function endedOf<R extends Row>(tables: readonly Table<R>[]): (R & { comparison: string })[] {
  return rowsOf(tables).filter((row) => row.ended_at !== null || row.why !== null);
}

/** The callers the comparisons rang, in the order they were named. */
export function callersOf(tables: readonly Table[]): string[] {
  return [...new Set(tables.flatMap((table) => (table.personas.length > 0 ? table.personas : [table.persona])))];
}

// Several comparisons are one table: a caller rung again under the same setup is another round of it.
// `read` says what each call's log added to its row; a reader with no log says it added nothing.
/** The benchmark of the comparisons named: their ended calls, each setup's numbers, the verdict against the bars. */
export function standingsOf<R extends Row>(tables: readonly Table<R>[], bars: Bars, read: (row: R & { comparison: string }) => Read): Standings {
  const ended = endedOf(tables);
  const calls = ended.map((row) => callOf(row, read(row)));
  numberRounds(calls);
  calls.sort((one, other) => one.started_at - other.started_at);
  const callers = callersOf(tables);
  const values = new Map<string, AgentValues>();
  for (const row of ended) if (!values.has(nameOf(row.against))) values.set(nameOf(row.against), row.against);
  const setups = [...values].map(([name, one]) => setupOf(one, calls.filter((call) => call.setup === name), callers, bars));
  setups.sort(byStanding);
  return { calls, setups, verdict: verdictOf(setups, bars) };
}
