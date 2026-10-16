/** Read a call's whole log by paging until a short page. */

import { type Entry } from "./wire/envelope.js";
import { LogPageSchema } from "./wire/rest.js";

import { read, type Credentials } from "./api";

// The gateway's largest page; a shorter page is the last one.
const A_WHOLE_PAGE = 500;

// Stopping on a short page avoids the 204 the door answers for a cursor past a sealed call's end.
/** Every entry of one call so far; rejects with 404 when the call has no log yet. */
export async function wholeLog(credentials: Credentials, call: string): Promise<Entry[]> {
  const whole: Entry[] = [];
  let cursor = 0;
  for (;;) {
    const page = LogPageSchema.parse(
      await read(credentials, `/v1/calls/${call}/events`, { after: cursor, limit: A_WHOLE_PAGE }),
    );
    whole.push(...page.entries);
    if (page.next === null || page.entries.length < A_WHOLE_PAGE) {
      return whole;
    }
    cursor = page.next;
  }
}
