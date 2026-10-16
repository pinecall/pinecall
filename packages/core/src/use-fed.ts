/** Read a door when the feed says it changed: once on open, on every matching entry, and on a clock only while the feed is down. */

import { useEffect, useRef } from "react";

import { useCredentials } from "./credentials";
import { feedOf, type FeedDoor } from "./feed";
import type { Connection } from "./stream";
import type { Entry } from "./wire/envelope.js";

// While the feed is down nothing says what changed, so the door is read at this pace until it is back.
const EVERY_MS = 3000;

/** How a door is asked for: every `every` ms while the feed is down, once as it comes back, never while it is live. */
export interface Pace {
  connected(now: Connection): void;
  stop(): void;
}

/** Start pacing `ask`, the feed not yet open: until it is, the door is polled. */
export function paced(ask: () => void, every = EVERY_MS): Pace {
  let polling: number | undefined = window.setInterval(ask, every);
  const quiet = (): void => {
    window.clearInterval(polling);
    polling = undefined;
  };
  return {
    connected(now) {
      if (now === "live") {
        // What changed while it was down was never said: read once, then let the feed speak.
        if (polling !== undefined) ask();
        quiet();
      } else if (polling === undefined) {
        polling = window.setInterval(ask, every);
      }
    },
    stop: quiet,
  };
}

/** What a reader wants of the feed besides its reads. */
export interface Fed {
  /** The door that streams: the org's feed unless said otherwise. */
  door?: FeedDoor;
  /** The entry types that call for a read; every entry when left out. */
  types?: readonly string[];
  /** Of those, the entries that call for a read; every one when left out. */
  when?: (entry: Entry) => boolean;
  /** Every entry of the feed, whether or not it calls for a read. */
  onEntry?: (entry: Entry) => void;
  onConnection?: (connection: Connection) => void;
  onRefused?: (why: string) => void;
}

/** Call `ask` on open, when the feed speaks of one of `fed.types` that `fed.when` accepts, and by the clock while it is down. */
export function useFed(ask: () => void, fed: Fed = {}, deps: readonly unknown[] = []): void {
  const credentials = useCredentials();
  // The latest closures, read by the subscription without resubscribing on every render.
  const latest = useRef({ ask, fed });
  latest.current = { ask, fed };

  useEffect(() => {
    const again = (): void => latest.current.ask();
    const pace = paced(again);
    again();
    let settling = true;
    const stop = feedOf(credentials, fed.door).listen({
      onEntry(entry) {
        const { types, when, onEntry } = latest.current.fed;
        onEntry?.(entry);
        if ((types === undefined || types.includes(entry.type)) && (when === undefined || when(entry))) again();
      },
      onConnection(now) {
        latest.current.fed.onConnection?.(now);
        // A feed already live as this reader joins was read a line above: that read stands.
        if (settling && now === "live") pace.stop();
        else pace.connected(now);
      },
      onRefused: (why) => latest.current.fed.onRefused?.(why),
    });
    settling = false;
    return () => {
      pace.stop();
      stop();
    };
    // `deps` are what the read depends on: a new door or window reads afresh.
  }, [credentials, ...deps]);
}
