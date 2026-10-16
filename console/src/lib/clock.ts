/** Timestamp formatting: UTC to the second. */

import { NOTHING } from "@pinecall/core/calls";

// Always UTC so readers in different timezones compare the same digits.
/** Unix seconds as `YYYY-MM-DD hh:mm:ss`, or a dash for null. */
export function started(at: number | null): string {
  if (at === null) {
    return NOTHING;
  }
  return new Date(at * 1000).toISOString().slice(0, 19).replace("T", " ");
}
