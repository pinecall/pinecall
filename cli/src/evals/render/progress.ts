/** Live progress of a suite on a terminal: the header, a line per golden as it is judged, a bar, redrawn in place. */

import type { Writable } from "node:stream";

import type { EvalRun } from "../service/index.js";
import { cellOf } from "./matrix.js";

const OPEN = "○";
const READING = "reading…";
const BAR_WIDTH = 20;
const FILLED = "█";
const EMPTY = "░";
// Call id prefix length on live lines; the full id is in the report.
const CALL_SHOWN = 12;
// Fallback width: a pty with no window size reports 0 columns.
const TERMINAL_WIDTH = 80;

/** What is known about the run before the gateway has stored it. */
export interface Watched {
  agent: string;
  goldens: number;
  /** Cases played beside them: a count when named, `dataset` when the whole of it is. */
  cases?: number | "dataset" | undefined;
  /** Model names for display: the declared model, or those named. */
  models: string[];
  declaredAs: string;
  /** The goldens sent from disk, so each judged line can say `file` or `case`. */
  files?: ReadonlySet<string> | undefined;
}

/** Header line: agent, golden count, the cases played, models and run id. */
export function header(watched: Watched, id: string): string {
  const counted = watched.goldens > 0 || watched.cases === undefined ? [`${watched.goldens} golden${watched.goldens === 1 ? "" : "s"}`] : [];
  if (watched.cases === "dataset") counted.push("the dataset");
  else if (watched.cases !== undefined) counted.push(`${watched.cases} case${watched.cases === 1 ? "" : "s"}`);
  return [watched.agent, ...counted, ...watched.models, id].join(" · ");
}

/** The block drawn while a run goes: judged cells, calls still being read, the bar. */
export function progress(run: EvalRun, watched: Watched, startedAt: number): string[] {
  const lines: string[] = [];
  let heading: string | undefined;
  for (const cell of run.matrix?.runs ?? []) {
    if (watched.models.length > 1 && cell.model !== heading) {
      heading = cell.model;
      lines.push(`  ${cell.model === "declared" ? watched.declaredAs : cell.model}`);
    }
    lines.push(...cellOf(run, cell, watched.declaredAs, watched.files));
  }
  const judged = run.matrix?.runs.length ?? 0;
  for (const opened of run.calls.slice(judged)) lines.push(`  ${OPEN} ${opened.golden}  ${opened.call.slice(0, CALL_SHOWN)}…  ${READING}`);
  lines.push(bar(judged, totalOf(watched), startedAt));
  return lines;
}

// A run of the whole dataset has no total this side knows: it counts what was judged.
function totalOf(watched: Watched): number | null {
  if (watched.cases === "dataset") return null;
  return (watched.goldens + (watched.cases ?? 0)) * Math.max(watched.models.length, 1);
}

function bar(judged: number, total: number | null, startedAt: number): string {
  const seconds = Math.round((Date.now() - startedAt) / 1000);
  if (total === null) return `${judged} judged · ${seconds}s`;
  const filled = total === 0 ? BAR_WIDTH : Math.round((judged / total) * BAR_WIDTH);
  return `[${FILLED.repeat(filled)}${EMPTY.repeat(BAR_WIDTH - filled)}] ${judged}/${total} · ${seconds}s`;
}

type Write = (...args: unknown[]) => boolean;

/**
 * A block redrawn in place at the bottom of the terminal. Other writes to the terminal would break
 * the cursor-up count, so every sharing stream's `write` is wrapped to erase the block first.
 */
export class BottomBlock {
  #rows = 0;
  readonly #write: Write;
  readonly #borrowed = new Map<{ write: Write }, Write>();

  constructor(private readonly out: Writable) {
    this.#write = (out as unknown as { write: Write }).write.bind(out) as Write;
  }

  /** Wrap `write` on this stream and the sharing ones. */
  own(sharing: Writable[]): void {
    for (const stream of [this.out, ...sharing]) {
      const owned = stream as unknown as { write: Write };
      if (this.#borrowed.has(owned)) continue;
      const raw = owned.write.bind(stream) as Write;
      this.#borrowed.set(owned, raw);
      owned.write = (...args: unknown[]) => {
        this.erase();
        return raw(...args);
      };
    }
  }

  /** Restore every wrapped `write`. */
  giveBack(): void {
    for (const [owned, raw] of this.#borrowed) owned.write = raw;
    this.#borrowed.clear();
  }

  /** Redraw the block over the previous one. */
  draw(lines: string[]): void {
    // Count wrapped rows, not lines, or the next redraw lands mid-block.
    const columns = (this.out as NodeJS.WriteStream).columns || TERMINAL_WIDTH;
    const climb = this.#rows > 0 ? `\x1b[${this.#rows}A` : "";
    this.#write(`${climb}\x1b[0J${lines.map((line) => `${line}\n`).join("")}`);
    this.#rows = lines.reduce((rows, line) => rows + Math.max(1, Math.ceil([...line].length / columns)), 0);
  }

  /** Clear the block, leaving the cursor where it began. */
  erase(): void {
    if (this.#rows > 0) this.draw([]);
  }
}
