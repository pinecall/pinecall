// Log reading: one URL served as a JSON page or SSE, folded by the protocol's reducer.

import { decodeEntry, eventOf } from "../wire/codec.js";
import { type Entry } from "../wire/envelope.js";
import { apply, initialState } from "../wire/reduce.js";
import { type State } from "../wire/state.js";
import { agentLogUrl, callLogUrl, feedUrl } from "./endpoints.js";
import { PinecallError } from "./frames.js";
import { camelEvent, type CamelEvent } from "./listeners.js";
import { sseFrames } from "./sse.js";
import { signed, type World } from "./signed.js";

/** A call's log, an agent's own log, or the org's feed (live only: it has no cursor and no end). */
export type LogTarget =
  | { call: string; agent?: never; feed?: never }
  | { agent: string; call?: never; feed?: never }
  | { feed: true; call?: never; agent?: never };

/** Connection and cursor options for reading a log. */
export interface ReadOptions {
  url: string;
  apiKey: string;
  /** The world to read from; omitted means sandbox. */
  env?: World;
  after?: number;
  /** Only these entry types, filtered by the gateway. */
  types?: readonly string[];
  /** Called each time a connection opens, the first and every reconnect: what changed while it was down was never said. */
  onOpen?: () => void;
  signal?: AbortSignal;
}

/** One page of a log: entries after the cursor, their folded state, and the next cursor. */
export interface Page {
  entries: Entry[];
  state: State;
  /** True while the log is still open and more entries will follow. */
  live: boolean;
  /** The cursor for the next page, or null when nothing follows. */
  next: number | null;
}

/** One entry, its decoded event, and the folded state including it. */
export interface Observation {
  entry: Entry;
  event: CamelEvent;
  state: State;
}

/**
 * Stream a log from the cursor onward, until aborted.
 *
 * A dropped stream reconnects with `Last-Event-ID`; a reader that fell behind receives `log.gap`
 * (with a snapshot when available) and then `log.caught_up`. Throws only if the first connection
 * fails.
 */
export async function* observe(target: LogTarget, options: ReadOptions): AsyncGenerator<Observation> {
  let state = initialState();
  const url = new URL(doorOf(target, options.url));
  const after = options.after ?? 0;
  if (after > 0) {
    url.searchParams.set("after", String(after));
  }
  if (options.types !== undefined) {
    url.searchParams.set("types", options.types.join(","));
  }
  const streaming = { apiKey: options.apiKey, env: options.env, onOpen: options.onOpen, signal: options.signal };
  for await (const frame of sseFrames(url, { ...streaming, lastId: after > 0 ? String(after) : undefined })) {
    if (frame.data === "") {
      continue;
    }
    const entry = decodeEntry(JSON.parse(frame.data) as unknown);
    state = apply(state, entry);
    yield { entry, event: camelEvent(eventOf(entry)), state };
  }
}

/**
 * Read one page of a log after the cursor. Use `next` rather than the last entry's seq: an empty
 * page of a live log still has one.
 */
export async function history(target: LogTarget, options: ReadOptions): Promise<Page> {
  const response = await read(target, options, "application/json");
  const page: unknown = await response.json();
  if (page === null || typeof page !== "object" || !Array.isArray((page as { entries?: unknown }).entries)) {
    throw new PinecallError("the log page is not { entries, live, next }");
  }
  const { entries: raw, live, next } = page as { entries: unknown[]; live?: unknown; next?: unknown };
  const entries = raw.map((one: unknown) => decodeEntry(one));
  return {
    entries,
    state: entries.reduce(apply, initialState()),
    live: live === true,
    next: typeof next === "number" ? next : null,
  };
}

async function read(target: LogTarget, options: ReadOptions, accept: string): Promise<Response> {
  const url = new URL(doorOf(target, options.url));
  if (options.types !== undefined) {
    url.searchParams.set("types", options.types.join(","));
  }
  const after = options.after ?? 0;
  if (after > 0) {
    url.searchParams.set("after", String(after));
  }
  const headers: Record<string, string> = { accept, ...signed(options.apiKey, options.env) };
  if (after > 0) {
    headers["last-event-id"] = String(after);
  }
  const response = await fetch(url, { headers, ...(options.signal === undefined ? {} : { signal: options.signal }) });
  if (!response.ok) {
    throw new PinecallError(`${url.pathname}: the gateway answered ${response.status}`);
  }
  return response;
}

function doorOf(target: LogTarget, base: string): string {
  if (target.feed === true) {
    return feedUrl(base);
  }
  return target.call === undefined ? agentLogUrl(base, target.agent) : callLogUrl(base, target.call);
}
