/** Extracts the recalled memory words that `remembers()` checks against. */

import { type Camel } from "../wire/codec.js";
import { type MemoryOps } from "../wire/events.js";

/**
 * Each recalled fact's text and category from one `memory.ops` entry. Only `recall` ops count:
 * a `remember` stores facts from this call rather than surfacing them to it.
 */
export function wordsRecalled(entry: Camel<MemoryOps>): string[] {
  return entry.ops
    .filter((op) => op.op === "recall")
    .flatMap((op) => op.facts.flatMap((fact) => [fact.text, fact.category ?? ""]));
}
