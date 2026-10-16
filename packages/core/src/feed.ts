/** The org's feed (`/v1/events`) or the box's floor (`/v1/ops/events`), each opened once per page and shared by everything that reads on it. */

import { doorUrl, type Credentials } from "./api";
import { openLog, type Connection } from "./stream";
import type { Entry } from "./wire/envelope.js";

/** What a reader of the feed hears. */
export interface FeedListener {
  onEntry(entry: Entry): void;
  /** Called at once with the connection as it stands, then on every change. */
  onConnection(connection: Connection): void;
  /** An undecodable frame or a refused stream; the connection's own state says what follows. */
  onRefused?(why: string): void;
}

/** One connection to the feed, opened with its first listener and closed with its last. */
export interface Feed {
  listen(listener: FeedListener): () => void;
}

/** The two doors that stream the lifecycle: the org's own feed, and the operator's floor of every org's. */
export type FeedDoor = "/v1/events" | "/v1/ops/events";

// A frame of the box's floor wraps the entry with whose it is.
const ENTRY_OF: Record<FeedDoor, (frame: unknown) => unknown> = {
  "/v1/events": (frame) => frame,
  "/v1/ops/events": (frame) => (frame as { entry: unknown }).entry,
};

const feeds = new WeakMap<Credentials, Map<FeedDoor, Feed>>();

/** The feed of this key at this door: the same object each time, so a page holds one stream of each. */
export function feedOf(credentials: Credentials, door: FeedDoor = "/v1/events"): Feed {
  const held = feeds.get(credentials) ?? new Map<FeedDoor, Feed>();
  feeds.set(credentials, held);
  let feed = held.get(door);
  if (feed === undefined) {
    feed = sharedFeed((reader) => openLog(doorUrl(credentials, door), credentials, reader, ENTRY_OF[door]));
    held.set(door, feed);
  }
  return feed;
}

/** A feed over `open`, which starts a stream and answers how to stop it. Exported for the tests. */
export function sharedFeed(open: (reader: Parameters<typeof openLog>[2]) => () => void): Feed {
  const listeners = new Set<FeedListener>();
  let connection: Connection = "connecting";
  let close: (() => void) | undefined;

  return {
    listen(listener) {
      listeners.add(listener);
      if (close === undefined) {
        connection = "connecting";
        close = open({
          onEntry: (entry) => listeners.forEach((each) => each.onEntry(entry)),
          onPaint: () => undefined,
          onConnection: (now) => {
            connection = now;
            listeners.forEach((each) => each.onConnection(now));
          },
          onRefused: (why) => listeners.forEach((each) => each.onRefused?.(why)),
        });
      } else {
        listener.onConnection(connection);
      }
      return () => {
        listeners.delete(listener);
        if (listeners.size === 0 && close !== undefined) {
          close();
          close = undefined;
        }
      };
    },
  };
}
