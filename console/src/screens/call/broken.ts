/** Where the judges a call broke put their finger: each line they cite, on the row of the timeline that holds it. */

import type { CallScore } from "@pinecall/core/wire/events-call";

import type { Row } from "./timeline-rows";

/** One judge that broke on a row, and why, in its own words. */
export interface Broke {
  judge: string;
  reason: string;
}

// What a judge points at: what was said and what was done. A state change or a quiet stretch is
// read past to the row before it.
const POINTED_AT: readonly Row["kind"][] = ["turn", "tool", "confirm"];

/**
 * For each row's seq, the judges that broke on it. A judge cites seqs of the log, and a seq no row
 * of these kinds carries (a tool's result, a state change after it) belongs to the row before it.
 */
export function brokenAt(score: CallScore | null, rows: readonly Row[]): Map<number, Broke[]> {
  const at = new Map<number, Broke[]>();
  if (score === null) return at;
  const seqs = [...new Set(rows.filter((row) => POINTED_AT.includes(row.kind)).map((row) => row.seq))].sort((one, other) => one - other);
  for (const judgment of score.judges) {
    if (judgment.verdict !== "broken") continue;
    const held = new Set(judgment.evidence.seqs.map((seq) => holding(seqs, seq)).filter((seq): seq is number => seq !== undefined));
    for (const seq of held) at.set(seq, [...(at.get(seq) ?? []), { judge: judgment.name, reason: judgment.reason }]);
  }
  return at;
}

function holding(seqs: readonly number[], cited: number): number | undefined {
  let found: number | undefined;
  for (const seq of seqs) {
    if (seq > cited) break;
    found = seq;
  }
  return found;
}
