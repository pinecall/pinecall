/** Follow one call: fold the log so far, then stream new entries over SSE. */

import { type Entry } from "./wire/envelope.js";
import { apply, initialState } from "./wire/reduce.js";
import { TERMINAL_EVENT } from "./wire/registry.js";
import { type CustomNote, type State } from "./wire/state.js";
import { useEffect, useRef, useState } from "react";

import { GatewayError, doorUrl, type Credentials } from "./api";
import { useCredentials } from "./credentials";
import { wholeLog } from "./log-pages";
import { openLog, type Connection } from "./stream";

/** Per-entry callbacks, fired immediately rather than on paint. */
export interface CallOptions {
  onEntry?: (entry: Entry) => void;
  onCustom?: (note: CustomNote) => void;
}

/** The call's folded state and stream status. */
export interface CallLog {
  state: State;
  connection: Connection;
  error: string | null;
}

// The reducer mutates arrays in place, so `state.turns` keeps its identity as it grows:
// memoise on `state.seq`, never on an array.
/** Follow one call; resumes from the last seq on reconnect. */
export function useCall(call: string, options: CallOptions = {}): CallLog {
  const credentials = useCredentials();
  const [state, setState] = useState<State>(initialState);
  const [connection, setConnection] = useState<Connection>("connecting");
  const [error, setError] = useState<string | null>(null);
  const heard = useRef<CallOptions>(options);

  useEffect(() => {
    heard.current = options;
  });

  useEffect(() => {
    const folded = { current: initialState() };
    let stopped = false;
    let close: (() => void) | null = null;

    const paint = (): void => setState({ ...folded.current });
    const stop = (): void => {
      stopped = true;
      close?.();
    };

    void (async () => {
      let cursor = 0;
      try {
        cursor = await seed(credentials, call, folded, heard);
      } catch (refused) {
        setError(String(refused));
        setConnection("ended");
        return;
      }
      if (stopped) {
        return;
      }
      paint();
      if (folded.current.status === "ended") {
        setConnection("ended");
        return;
      }
      close = openLog(doorUrl(credentials, `/v1/calls/${call}/events`, { after: cursor }), credentials, {
        onEntry(entry) {
          folded.current = apply(folded.current, entry);
          heard.current.onEntry?.(entry);
          told(entry, folded.current, heard.current);
          // Nothing follows the terminal entry; close instead of reconnecting into a 204.
          if (entry.type === TERMINAL_EVENT) {
            paint();
            setConnection("ended");
            stop();
          }
        },
        onPaint: paint,
        onConnection: setConnection,
        onRefused: setError,
      });
      if (stopped) {
        close();
      }
    })();

    return stop;
  }, [call, credentials]);

  return { state, connection, error };
}

// Fold the log so far and return the last seq. A 404 (log not opened yet) starts from zero.
async function seed(
  credentials: Credentials,
  call: string,
  folded: { current: State },
  heard: { current: CallOptions },
): Promise<number> {
  let entries: Entry[];
  try {
    entries = await wholeLog(credentials, call);
  } catch (refused) {
    if (refused instanceof GatewayError && refused.status === 404) {
      return 0;
    }
    throw refused;
  }
  for (const entry of entries) {
    folded.current = apply(folded.current, entry);
    heard.current.onEntry?.(entry);
    told(entry, folded.current, heard.current);
  }
  return entries.at(-1)?.seq ?? 0;
}

// Forward the custom note the reducer just stored.
function told(entry: Entry, state: State, options: CallOptions): void {
  if (entry.type !== "custom") {
    return;
  }
  const note = state.custom.at(-1);
  if (note !== undefined) {
    options.onCustom?.(note);
  }
}
