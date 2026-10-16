/** The tenant's log relay in a test: a fetch that answers each URL from a script and remembers what it was asked. */

import { type Entry } from "../src/wire/envelope.js";

/** What one request to a URL is answered with, in the order the requests arrive. */
export type Scene =
  /** A stream: these chunks, then the body ends (a drop) or stays open for `push`. */
  | { stream: string[]; then: "end" | "hold" }
  /** A status and a body, and nothing streamed. */
  | { status: number; body?: string }
  /** The network failed before an answer. */
  | { fails: true };

/** One request the gateway saw. */
export interface Asked {
  url: string;
  lastEventId: string | null;
  accept: string | null;
  aborted: boolean;
}

/** One SSE frame for an entry, as the gateway writes it. */
export function frame(entry: Entry | { seq: number; type: string }, data = JSON.stringify(entry)): string {
  return `id: ${entry.seq}\nevent: ${entry.type}\ndata: ${data}\n\n`;
}

/** Every entry as frames, joined: one chunk. */
export function framed(entries: readonly Entry[]): string {
  return entries.map((entry) => frame(entry)).join("");
}

/** Until the bytes the gateway queued have been read, whatever the fake timers are doing. */
export async function settle(): Promise<void> {
  for (let turn = 0; turn < 10; turn++) await new Promise<void>((done) => setImmediate(done));
}

export class FakeGateway {
  readonly requests: Asked[] = [];
  readonly #scripts = new Map<string, Scene[]>();
  readonly #journal: string[];
  #open: ReadableStreamDefaultController<Uint8Array> | null = null;

  /** `journal` is shared with a fake LiveKit when a test asks which happened first. */
  constructor(journal: string[] = []) {
    this.#journal = journal;
  }

  /** The next requests to `url` are answered with these scenes, in order. */
  answer(url: string, ...scenes: Scene[]): this {
    this.#scripts.set(url, [...(this.#scripts.get(url) ?? []), ...scenes]);
    return this;
  }

  /** More bytes on the stream that is open now. */
  push(text: string): void {
    this.#open?.enqueue(new TextEncoder().encode(text));
  }

  /** The open stream ends, the way a relay restarting ends it. */
  drop(): void {
    this.#open?.close();
    this.#open = null;
  }

  readonly fetch: typeof fetch = async (input, init) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const headers = new Headers(init?.headers);
    const asked: Asked = {
      url,
      lastEventId: headers.get("last-event-id"),
      accept: headers.get("accept"),
      aborted: false,
    };
    this.requests.push(asked);
    this.#journal.push(`log ${url}`);
    const signal = init?.signal;
    if (signal?.aborted) throw new DOMException("aborted", "AbortError");
    const scene = this.#scripts.get(url)?.shift();
    if (scene === undefined) return new Response(`no script for ${url}`, { status: 404 });
    if ("fails" in scene) throw new TypeError("fetch failed");
    if ("status" in scene) return new Response(scene.body ?? null, { status: scene.status });
    const body = new ReadableStream<Uint8Array>({
      start: (controller) => {
        for (const chunk of scene.stream) controller.enqueue(new TextEncoder().encode(chunk));
        if (scene.then === "end") controller.close();
        else this.#open = controller;
        signal?.addEventListener("abort", () => {
          asked.aborted = true;
          if (this.#open === controller) this.#open = null;
          controller.error(new DOMException("aborted", "AbortError"));
        });
      },
    });
    return new Response(body, { status: 200, headers: { "content-type": "text/event-stream" } });
  };
}
