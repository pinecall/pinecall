/** SSE log reader over fetch, with reconnect and throttled paints. */

import { decodeEntry } from "./wire/codec.js";
import { type Entry } from "./wire/envelope.js";

import { headersFor, type Credentials } from "./api";

/** Stream connection status. */
export type Connection = "connecting" | "live" | "reconnecting" | "ended";

// Throttle repaints so bursts of interim transcripts don't redraw dozens of times a second.
export const FRAME_MS = 100;

// Reconnect backoff: doubles up to the ceiling.
const RECONNECT_MS = 500;
const RECONNECT_CEILING_MS = 8_000;

// The gateway answers 204 for the stream of a finished call.
const NOTHING_MORE = 204;

/** Callbacks for a log stream. */
export interface LogReader {
  /** Each entry, in seq order, as it arrives. */
  onEntry: (entry: Entry) => void;
  /** Called at most once per FRAME_MS, only after new entries. */
  onPaint: () => void;
  onConnection: (connection: Connection) => void;
  /** An undecodable frame; the stream continues. */
  onRefused: (why: string) => void;
}

/** One parsed SSE message; data lines joined with newlines. */
export interface SseMessage {
  id: string | null;
  event: string | null;
  data: string;
}

// EventSource can't set headers and the key must not go in a URL, so SSE is parsed by hand over
// fetch, sending Last-Event-ID ourselves on reconnect.
/** Incremental SSE parser: feed chunks, get complete messages in order. */
export class SseParser {
  #buffer = "";
  #id: string | null = null;
  #event: string | null = null;
  #data: string[] = [];

  feed(chunk: string): SseMessage[] {
    this.#buffer += chunk;
    const messages: SseMessage[] = [];
    let at: number;
    while ((at = this.#buffer.search(/\r\n|\n|\r/)) !== -1) {
      const line = this.#buffer.slice(0, at);
      this.#buffer = this.#buffer.slice(at + (this.#buffer.startsWith("\r\n", at) ? 2 : 1));
      const done = this.#line(line);
      if (done !== null) messages.push(done);
    }
    return messages;
  }

  // A blank line ends a message; a line starting with `:` is a comment; otherwise `field: value`.
  #line(line: string): SseMessage | null {
    if (line === "") {
      if (this.#data.length === 0 && this.#event === null && this.#id === null) return null;
      const message: SseMessage = { id: this.#id, event: this.#event, data: this.#data.join("\n") };
      this.#event = null;
      this.#data = [];
      return message;
    }
    if (line.startsWith(":")) return null;
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    const value = colon === -1 ? "" : line.slice(colon + 1).replace(/^ /, "");
    if (field === "id") this.#id = value;
    else if (field === "event") this.#event = value;
    else if (field === "data") this.#data.push(value);
    return null;
  }
}

/** What a stream hands its reader: each frame, and how the connection is going. */
export interface SseReader {
  onMessage: (message: SseMessage) => void;
  onConnection: (connection: Connection) => void;
  /** The gateway refused the stream; it does not reconnect. */
  onRefusedStream: (why: string) => void;
}

/**
 * Open an SSE stream over fetch: it reconnects with the last id and a backoff, and ends on a 204.
 * Returns a function that closes it.
 */
export function openSse(url: string, credentials: Credentials, reader: SseReader): () => void {
  const controller = new AbortController();
  let lastId: string | null = null;
  let backoff = RECONNECT_MS;
  let ours = true;

  const connect = async (): Promise<void> => {
    while (ours) {
      let answer: Response;
      try {
        answer = await fetch(url, {
          headers: { ...headersFor(credentials), accept: "text/event-stream", ...(lastId === null ? {} : { "last-event-id": lastId }) },
          signal: controller.signal,
        });
      } catch {
        if (!ours) return;
        reader.onConnection("reconnecting");
        await slept(backoff, controller.signal);
        backoff = Math.min(backoff * 2, RECONNECT_CEILING_MS);
        continue;
      }
      if (answer.status === NOTHING_MORE) {
        reader.onConnection("ended");
        return;
      }
      if (!answer.ok || answer.body === null) {
        reader.onRefusedStream(`the stream answered ${answer.status}`);
        reader.onConnection("ended");
        return;
      }
      reader.onConnection("live");
      backoff = RECONNECT_MS;
      const parser = new SseParser();
      const decoder = new TextDecoder();
      const body = answer.body.getReader();
      try {
        for (;;) {
          const { value, done } = await body.read();
          if (done) break;
          for (const message of parser.feed(decoder.decode(value, { stream: true }))) {
            if (message.id !== null) lastId = message.id;
            reader.onMessage(message);
          }
        }
      } catch {
        if (!ours) return;
      }
      if (!ours) return;
      // Body ended without a 204: the gateway dropped mid-stream, so resume.
      reader.onConnection("reconnecting");
      await slept(backoff, controller.signal);
      backoff = Math.min(backoff * 2, RECONNECT_CEILING_MS);
    }
  };

  reader.onConnection("connecting");
  void connect();

  return () => {
    ours = false;
    controller.abort();
  };
}

/**
 * Open a log stream; returns a function that closes it. `shape` takes the entry out of a frame
 * whose data wraps it (the box's floor does), and leaves a frame that is the entry as it is.
 */
export function openLog(url: string, credentials: Credentials, reader: LogReader, shape: (frame: unknown) => unknown = (frame) => frame): () => void {
  let paint: number | null = null;

  const schedule = (): void => {
    if (paint !== null) return;
    paint = window.setTimeout(() => {
      paint = null;
      reader.onPaint();
    }, FRAME_MS);
  };

  const close = openSse(url, credentials, {
    onMessage(message) {
      if (message.data === "") return;
      try {
        reader.onEntry(decodeEntry(shape(JSON.parse(message.data))));
      } catch (refused) {
        reader.onRefused(String(refused));
        return;
      }
      schedule();
    },
    onConnection: reader.onConnection,
    onRefusedStream: reader.onRefused,
  });

  return () => {
    if (paint !== null) window.clearTimeout(paint);
    close();
  };
}

function slept(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((wake) => {
    const timer = window.setTimeout(wake, ms);
    signal.addEventListener("abort", () => {
      window.clearTimeout(timer);
      wake();
    }, { once: true });
  });
}
