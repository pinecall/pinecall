/** Where the judges a call broke put their finger: each line they cite, on the row that holds it, and the light that shows a line cited. */

import type { CallScore } from "@pinecall/core/wire/events-call";
import type { Row } from "./timeline-rows";

/** One judge that broke on a row, and why, in its own words. */
export interface Broke {
  judge: string;
  reason: string;
}

// What a judge points at: what was said and what was done. A state change or a quiet stretch is read past to the row before it.
const POINTED_AT: readonly Row["kind"][] = ["turn", "tool", "confirm"];

/** Whether a judge's citation can land on this row: such a row carries `data-seq` on the page. */
export function canBeCited(row: Row): boolean {
  return POINTED_AT.includes(row.kind);
}

/** For each row's seq, the judges that broke on it. A seq no such row carries (a tool's result, a state change after it) belongs to the row before it. */
export function brokenAt(score: CallScore | null, rows: readonly Row[]): Map<number, Broke[]> {
  const at = new Map<number, Broke[]>();
  if (score === null) return at;
  const seqs = [...new Set(rows.filter(canBeCited).map((row) => row.seq))].sort((one, other) => one - other);
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

const LIT_MS = 1800;

/** Scroll to the row that holds a cited seq and light it for a moment. Whichever way the call is being read, its rows carry `data-seq`. */
export function spotlight(within: HTMLElement | null, cited: number): void {
  if (within === null) return;
  let row: HTMLElement | null = null;
  let best = -1;
  for (const one of within.querySelectorAll<HTMLElement>("[data-seq]")) {
    const seq = Number(one.dataset["seq"]);
    if (seq <= cited && seq > best) {
      row = one;
      best = seq;
    }
  }
  if (row === null) return;
  const lit = row;
  const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  lit.scrollIntoView({ block: "center", behavior: still ? "auto" : "smooth" });
  // Taken off and put back, so a second click on the same citation lights it again.
  lit.classList.remove("calls-lit");
  void lit.offsetWidth;
  lit.classList.add("calls-lit");
  window.setTimeout(() => lit.classList.remove("calls-lit"), LIT_MS);
}
