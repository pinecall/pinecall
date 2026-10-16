/** Hook to watch a call: reduced state for the panels, raw entries for the timeline. */

import { type Entry } from "@pinecall/core/wire/envelope";
import { type State } from "@pinecall/core/wire/state";
import { useMemo, useRef } from "react";

import { useCall } from "@pinecall/core/use-call";
import type { Connection } from "@pinecall/core/stream";

export interface WatchedCall {
  state: State;
  entries: Entry[];
  connection: Connection;
  error: string | null;
}

/**
 * Entries are kept alongside the state because turns carry no seq and the timeline needs log order.
 * Memoised on state.seq, which changes on every update.
 */
export function useWatchedCall(call: string): WatchedCall {
  const seen = useRef<Entry[]>([]);
  const log = useCall(call, {
    onEntry(entry) {
      // A remount or reconnect replays the log from the start; skip entries already kept.
      const last = seen.current.at(-1);
      if (last !== undefined && entry.seq <= last.seq) return;
      seen.current.push(entry);
    },
  });
  const entries = useMemo(() => [...seen.current], [log.state.seq]);
  return { state: log.state, entries, connection: log.connection, error: log.error };
}
