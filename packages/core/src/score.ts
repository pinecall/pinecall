/** Read a finished call's score entry. */

import { type CallScore, CallScoreSchema } from "./wire/events-call.js";
import { TERMINAL_EVENT } from "./wire/registry.js";
import { LogPageSchema } from "./wire/rest.js";

import { read, type Credentials } from "./api";

// `call.score` is the terminal entry, so on a finished call it sits at `last_seq`: one request
// instead of paging the whole log.
/** The call's score, or null when the log carries none. */
export async function readScore(
  credentials: Credentials,
  call: string,
  lastSeq: number,
): Promise<CallScore | null> {
  if (lastSeq <= 0) {
    return null;
  }
  const page = LogPageSchema.parse(
    await read(credentials, `/v1/calls/${encodeURIComponent(call)}/events`, {
      after: lastSeq - 1,
      types: TERMINAL_EVENT,
      limit: 1,
    }),
  );
  const sealed = page.entries.find((entry) => entry.type === TERMINAL_EVENT);
  return sealed === undefined ? null : CallScoreSchema.parse(sealed.data);
}
