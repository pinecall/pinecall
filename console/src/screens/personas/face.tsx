/** A persona's face: one of twenty-four drawn ones, on its tint — Pinecall's own by character, any other by its name. */

import type { ReactNode } from "react";

import { tintOf } from "../../ui";
import "./grid.css";

// Lorelei, by Lisa Wischofsky (CC0 1.0): drawn once, kept here as files, so a face costs one request
// and the page carries no avatar library. Sorted by name: a face's index is its number.
const FACES = Object.entries(import.meta.glob<string>("./faces/*.svg", { eager: true, query: "?url", import: "default" }))
  .sort(([one], [other]) => one.localeCompare(other))
  .map(([, url]) => url);

// Pinecall's own callers wear the face that suits them: the hurried one's brows, the one who
// talks over the agent mid-word, the one who keeps winking as they change their mind.
const OF_THE_LIBRARY: Readonly<Record<string, number>> = {
  "in-a-hurry": 12,
  "wrong-number": 5,
  "non-native": 8,
  interrupts: 6,
  "changes-mind": 15,
  "elderly-slow": 9,
  "angry-repeat-caller": 11,
  "asks-for-a-person": 2,
  "prompt-leak": 23,
  "data-leak": 3,
  "off-task": 19,
  harmful: 7,
  "unauthorized-action": 20,
};

/** The face number of a name: the library's by character, any other stable from its letters (FNV-1a). */
export function faceOf(name: string): number {
  const fixed = OF_THE_LIBRARY[name];
  if (fixed !== undefined) return fixed;
  let hash = 0x811c9dc5;
  for (const letter of name) hash = Math.imul(hash ^ (letter.codePointAt(0) ?? 0), 0x01000193);
  return (hash >>> 0) % FACES.length;
}

export function Face({ name, size = 64 }: { name: string; size?: number }): ReactNode {
  return (
    <span className={`psn-face ui-tile-mark psn-face-${tintOf(name)}`} style={{ width: size, height: size }} aria-hidden>
      <img src={FACES[faceOf(name)]} alt="" width={size} height={size} loading="lazy" />
    </span>
  );
}
