/** Watching one call: the reduced state for the panels, the raw entries for the conversation, and what the log concludes. */

import { useMemo, useRef } from "react";

import { type Connection } from "@pinecall/core/stream";
import { useCall } from "@pinecall/core/use-call";
import { type Entry } from "@pinecall/core/wire/envelope";
import { type CallScore, CallScoreSchema } from "@pinecall/core/wire/events-call";
import { TERMINAL_EVENT } from "@pinecall/core/wire/registry";
import { type State } from "@pinecall/core/wire/state";

export interface WatchedCall {
  state: State;
  entries: Entry[];
  connection: Connection;
  error: string | null;
}

/** Entries are kept beside the state because turns carry no seq and the rows need log order. Memoised on the state's seq, which moves on every update. */
export function useWatchedCall(call: string): WatchedCall {
  const seen = useRef<Entry[]>([]);
  const log = useCall(call, {
    onEntry(entry) {
      // A remount or a reconnect replays the log from the start: what is kept is not kept twice.
      const last = seen.current.at(-1);
      if (last !== undefined && entry.seq <= last.seq) return;
      seen.current.push(entry);
    },
  });
  const entries = useMemo(() => [...seen.current], [log.state.seq]);
  return { state: log.state, entries, connection: log.connection, error: log.error };
}

/** The verdict the log was sealed with, or null while it is not. An entry this page cannot read is no verdict. */
export function scoreIn(entries: readonly Entry[]): CallScore | null {
  const sealed = [...entries].reverse().find((entry) => entry.type === TERMINAL_EVENT);
  if (sealed === undefined) return null;
  const read = CallScoreSchema.safeParse(sealed.data);
  return read.success ? read.data : null;
}

/** The path of the call's audio, kept in its summary near the end of the log; null when nothing was recorded. */
export function recordingIn(entries: readonly Entry[]): string | null {
  const summary = [...entries].reverse().find((entry) => entry.type === "call.summary")?.data;
  const path = summary?.["recording"];
  return typeof path === "string" && path !== "" ? path : null;
}
