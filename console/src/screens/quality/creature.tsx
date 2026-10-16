/** A judge's creature: one of twenty-four soft shapes with two small eyes, chosen by its name — Pinecall's by what it asks, any other from its letters. */

import type { ReactNode } from "react";

// openavatars (Lohit, MIT — creatures/LICENSE), drawn once for these names and kept as files: a
// creature costs one request and the page takes no avatar library. Sorted by name: its index is
// its number.
const CREATURES = Object.entries(import.meta.glob<string>("./creatures/*.svg", { eager: true, query: "?url", import: "default" }))
  .sort(([one], [other]) => one.localeCompare(other))
  .map(([, url]) => url);

// Pinecall's own judges wear the one that suits the question: hearts for the one that asks whether
// the caller agreed, a stern pair of eyes for the one that asks whether a stop was honoured.
const OF_THE_LIBRARY: Readonly<Record<string, number>> = {
  consent: 2,
  disclosed: 7,
  "ended-well": 15,
  "expected-outcome": 23,
  grounded: 13,
  "honoured-stop": 11,
  identified: 10,
  promises: 9,
  relevance: 20,
  repetition: 3,
  sentiment: 1,
};

/** The creature number of a judge's name: the library's by character, any other stable from its letters (FNV-1a). */
export function creatureOf(name: string): number {
  const fixed = OF_THE_LIBRARY[name];
  if (fixed !== undefined) return fixed;
  let hash = 0x811c9dc5;
  for (const letter of name) hash = Math.imul(hash ^ (letter.codePointAt(0) ?? 0), 0x01000193);
  return (hash >>> 0) % CREATURES.length;
}

export function Creature({ name, size = 56 }: { name: string; size?: number }): ReactNode {
  return (
    <span className="qly-creature ui-tile-mark" style={{ width: size, height: size }} aria-hidden>
      <img src={CREATURES[creatureOf(name)]} alt="" width={size} height={size} loading="lazy" />
    </span>
  );
}
