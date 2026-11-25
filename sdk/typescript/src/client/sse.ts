// A server-sent stream over fetch: its frames from a cursor on, through every dropped connection.

import { PinecallError } from "./frames.js";
import { signed, type World } from "./signed.js";

/** One frame of a stream: its id, its event name, and its data lines joined by newlines. */
export interface Frame {
  id: string | null;
  event: string | null;
  data: string;
}

/** How a stream is opened. */
export interface Streaming {
  apiKey: string;
  /** The world to read from; omitted means sandbox. */
  env?: World | undefined;
  /** Resume after this id, as a reconnect does. */
  lastId?: string | undefined;
  /** Called each time a connection opens, the first and every reconnect. */
  onOpen?: (() => void) | undefined;
  signal?: AbortSignal | undefined;
}

const RETRY_MS = 1_000;
const RETRY_CAP_MS = 30_000;
// A first connection the gateway was too busy for, and said when to ask again (`503` with
// `Retry-After`: its database had no connection free), is no wrong key and no unknown door: it is
// opened again, this many times in all, before the refusal is thrown as any first failure is.
const A_BUSY_OPENING_IS_ASKED = 4;

// The gateway's answer for a stream with nothing more to say: a sealed call past its last entry.
const NOTHING_MORE = 204;

/**
 * The frames of a stream until aborted, or until the gateway answers 204: nothing more to say. A
 * dropped connection reconnects with `Last-Event-ID` after a jittered backoff; it throws only when
 * the first connection fails (a bad key, an unknown door), a gateway that said it was busy asked
 * again a few times first.
 */
export async function* sseFrames(url: URL | string, options: Streaming): AsyncGenerator<Frame> {
  let lastId = options.lastId ?? null;
  let attempt = 0;
  let opened = false;
  while (!aborted(options.signal)) {
    try {
      const response = await open(url, options, lastId);
      if (response.status === NOTHING_MORE) {
        return;
      }
      opened = true;
      attempt = 0;
      options.onOpen?.();
      for await (const frame of framesOf(response)) {
        if (frame.id !== null) {
          lastId = frame.id;
        }
        yield frame;
      }
    } catch (failed) {
      if (aborted(options.signal)) {
        return;
      }
      // Never opened means misconfiguration: surface it. Later drops retry, and so does a first
      // opening the gateway was only too busy for.
      if (!opened && !(failed instanceof Busy && attempt + 1 < A_BUSY_OPENING_IS_ASKED)) {
        throw failed;
      }
    }
    attempt += 1;
    await pause(Math.min(RETRY_CAP_MS, RETRY_MS * 2 ** (attempt - 1)) * Math.random(), options.signal);
  }
}

async function open(url: URL | string, options: Streaming, lastId: string | null): Promise<Response> {
  const headers: Record<string, string> = { accept: "text/event-stream", ...signed(options.apiKey, options.env) };
  if (lastId !== null) {
    headers["last-event-id"] = lastId;
  }
  const response = await fetch(url, { headers, ...(options.signal === undefined ? {} : { signal: options.signal }) });
  if (!response.ok) {
    const why = (await response.text()).trim();
    const said = `${new URL(url).pathname}: the gateway answered ${response.status}${why === "" ? "" : `: ${why}`}`;
    throw response.status === 503 && response.headers.has("retry-after") ? new Busy(said) : new PinecallError(said);
  }
  if (response.body === null && response.status !== NOTHING_MORE) {
    throw new PinecallError("the event stream came back with no body");
  }
  return response;
}

/** The gateway answered an opening `503` and said when to come back: busy for a moment, which asking again outlasts. */
class Busy extends PinecallError {}

/** The frames one connection carries, until it closes. */
async function* framesOf(response: Response): AsyncGenerator<Frame> {
  let buffered = "";
  const decoder = new TextDecoder();
  for await (const chunk of response.body as AsyncIterable<Uint8Array>) {
    buffered += decoder.decode(chunk, { stream: true });
    let cut = buffered.indexOf("\n\n");
    while (cut !== -1) {
      const frame = frameIn(buffered.slice(0, cut));
      buffered = buffered.slice(cut + 2);
      cut = buffered.indexOf("\n\n");
      if (frame !== null) {
        yield frame;
      }
    }
  }
}

/** Parse one block, or null for a comment or keep-alive. */
function frameIn(block: string): Frame | null {
  const lines = block.split("\n");
  const field = (name: string): string[] =>
    lines.filter((line) => line.startsWith(`${name}:`)).map((line) => line.slice(name.length + 1).replace(/^ /, ""));
  const data = field("data").join("\n");
  const id = field("id").at(-1) ?? null;
  const event = field("event").at(-1) ?? null;
  return data === "" && id === null ? null : { id, event, data };
}

// A function so TypeScript doesn't narrow `signal.aborted` across the loop.
function aborted(signal?: AbortSignal): boolean {
  return signal?.aborted === true;
}

async function pause(ms: number, signal?: AbortSignal): Promise<void> {
  await new Promise<void>((resolve) => {
    const timer = setTimeout(resolve, ms);
    signal?.addEventListener("abort", () => {
      clearTimeout(timer);
      resolve();
    });
  });
}
