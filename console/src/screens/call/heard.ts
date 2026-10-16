/** What the caller has said since their last turn landed: the stretches heard to the end, then what is heard now. */

import { type Entry } from "@pinecall/core/wire/envelope";

/**
 * The reducer's `live.user` is what the recognizer hears this instant, and empties the moment a
 * stretch is heard to the end — while the turn it belongs to lands a moment later, once the end of
 * the turn is decided. Read with the finals since the last `turn.user`, the words stay on screen
 * until their turn takes their place.
 */
export function heardSoFar(entries: readonly Entry[], hearing: string | null): string | null {
  const finals: string[] = [];
  for (let at = entries.length - 1; at >= 0; at -= 1) {
    const entry = entries[at]!;
    if (entry.type === "turn.user") break;
    if (entry.type === "user.transcript" && entry.data["final"] === true) finals.unshift(String(entry.data["text"] ?? ""));
  }
  const said = [...finals, ...(hearing === null ? [] : [hearing])].join(" ").replace(/\s+/g, " ").trim();
  return said === "" ? null : said;
}
