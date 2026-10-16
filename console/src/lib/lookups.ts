/** Timeline text for memory and retrieval lookups. */

import { type MemoryOp } from "@pinecall/core/wire/defs";
import { type DocsSources, type MemoryOps } from "@pinecall/core/wire/events";

/** `recall · 2 facts · 12 ms` — one clause per op when the entry carries several. */
export function memoryLine(data: MemoryOps): string {
  return data.ops.map(opLine).join("; ");
}

/** One line per fact touched by the ops. */
export function factLines(data: MemoryOps): string[] {
  return data.ops.flatMap((op) => op.facts.map((fact) => (fact.category ? `${fact.text} (${fact.category})` : fact.text)));
}

/** `3 sources · 41 ms` */
export function sourcesLine(data: DocsSources): string {
  return `${data.sources.length} sources · ${took(data.took_ms)}`;
}

/** One line per retrieved chunk: path, heading and score. */
export function sourceLines(data: DocsSources): string[] {
  return data.sources.map((source) => {
    const where = source.heading ? `${source.path} › ${source.heading}` : source.path;
    return `${where} · ${source.score.toFixed(3)}`;
  });
}

function opLine(op: MemoryOp): string {
  return `${op.op} · ${op.facts.length} facts · ${took(op.took_ms)}`;
}

function took(ms: number): string {
  return `${Math.round(ms)} ms`;
}
