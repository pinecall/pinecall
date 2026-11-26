/** A comparison read as a benchmark: its ended calls, each setup's numbers and the verdict against two bars, by the one implementation the CLI's report stands on (`@pinecall/agents/evals`). */

import { linesOf, notCountedOf, READ, recordingBegan, repliesOf, standingsOf, unpricedOf, type Bars, type Entry, type Line, type Standings } from "@pinecall/agents/evals";
import { read, type Credentials } from "@pinecall/core/api";

import type { Comparison } from "./door";

/** The bars a setup is held to until somebody moves them: nine calls in ten completed, a reply within a second and a half. */
export const THE_BARS: Bars = { floor: 0.9, ceiling_s: 1.5 };

/** What a call's log adds to its row: each reply it measured, the models nobody priced and, when its whole log was read, its lines. */
export interface Heard {
  replies_s: number[];
  unpriced: string[];
  timed: boolean;
  lines: Line[];
}

// The numbers stand on two kinds of entry; a report's lines on every kind a benchmark reads.
const THE_NUMBERS = ["turn.agent", "call.summary"] as const;
const A_PAGE = 200;
const READ_AT_ONCE = 6;

/** What one call's log adds to its row; `whole` reads its lines too, for a report that carries them. */
export async function readHeard(credentials: Credentials, row: { call: string; started_at: number }, whole: boolean = false): Promise<Heard> {
  const entries: Entry[] = [];
  let after = 0;
  for (;;) {
    const page = (await read(credentials, `/v1/calls/${encodeURIComponent(row.call)}/events`, { after, limit: A_PAGE, types: (whole ? READ : THE_NUMBERS).join(",") })) as { entries?: Entry[]; next?: number | null } | null;
    entries.push(...(page?.entries ?? []));
    const next = page?.next ?? null;
    if (next === null || next === after) break;
    after = next;
  }
  const began = recordingBegan(entries, row.started_at);
  return { replies_s: repliesOf(entries), unpriced: unpricedOf(entries), timed: whole && began.said, lines: whole ? linesOf(entries, began.at) : [] };
}

/** The calls named, a few at a time; a call whose log cannot be read is left out, and its row still counts. */
export async function readAllHeard(credentials: Credentials, rows: readonly { call: string; started_at: number }[], whole: boolean = false): Promise<Map<string, Heard>> {
  const found = new Map<string, Heard>();
  let next = 0;
  const taking = async (): Promise<void> => {
    for (let at = next++; at < rows.length; at = next++) {
      const row = rows[at];
      if (row === undefined) continue;
      try {
        found.set(row.call, await readHeard(credentials, row, whole));
      } catch {
        // Only the reply nine in ten are under, what went unpriced and the lines are read from the log.
      }
    }
  };
  await Promise.all(Array.from({ length: Math.min(READ_AT_ONCE, rows.length) }, taking));
  return found;
}

const NOT_READ: Heard = { replies_s: [], unpriced: [], timed: false, lines: [] };

// The console's gateway says on each row whether it counts, so no log is read to tell.
/** The benchmark of the comparisons named, with what was read of each call's log. */
export function benchmarkOf(tables: readonly Comparison[], bars: Bars, heard: ReadonlyMap<string, Heard>): Standings {
  return standingsOf(tables, bars, (row) => ({ not_counted: notCountedOf(row, []), recording: null, ...(heard.get(row.call) ?? NOT_READ) }));
}
