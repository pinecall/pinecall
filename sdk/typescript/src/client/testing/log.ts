// An in-memory fake of the call log's two read endpoints, fed by the test.

import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";
import { type Entry } from "../../wire/envelope.js";
import { EPHEMERAL_EVENTS, type EventType } from "../../wire/registry.js";

import { LOOPBACK } from "./loopback.js";

/** An attached SSE reader and its cursor. */
interface Reader {
  after: number;
  response: ServerResponse;
}

/**
 * Fake `GET /v1/calls/{id}/events` and `GET /v1/agents/{slug}/calls`, as JSON pages and SSE.
 * `after` and `Last-Event-ID` are the same cursor; a reconnecting reader gets exactly what it missed.
 */
export class FakeLog {
  readonly entries: Entry[] = [];
  readonly #server: Server;
  readonly #readers = new Set<Reader>();
  #port = 0;

  private constructor(server: Server) {
    this.#server = server;
  }

  /** Start on a random port. Close it when the test is over. */
  static async start(): Promise<FakeLog> {
    const server = createServer();
    const log = new FakeLog(server);
    server.on("request", (request, response) => log.#serve(request, response));
    await new Promise<void>((resolve) => server.listen(0, LOOPBACK, resolve));
    const address = server.address();
    log.#port = typeof address === "object" && address !== null ? address.port : 0;
    return log;
  }

  /** The URL to give a client as PINECALL_URL. */
  get url(): string {
    return `http://${LOOPBACK}:${this.#port}`;
  }

  /** Append one numbered entry and push it to attached readers. */
  append(agent: string, call: string | null, type: EventType, data: Record<string, unknown>): Entry {
    const entry: Entry = { seq: this.entries.length + 1, ts: Date.now() / 1000, call, agent, type, ephemeral: EPHEMERAL_EVENTS.has(type), data };
    this.entries.push(entry);
    for (const reader of this.#readers) {
      this.#push(reader, entry);
    }
    return entry;
  }

  /** End every attached stream, simulating a deploy. */
  cut(): void {
    for (const reader of this.#readers) {
      reader.response.end();
    }
    this.#readers.clear();
  }

  /** Number of attached readers. */
  get readers(): number {
    return this.#readers.size;
  }

  /** Stop listening and close all streams. */
  async close(): Promise<void> {
    this.cut();
    await new Promise<void>((resolve, reject) => this.#server.close((failed) => (failed ? reject(failed) : resolve())));
  }

  #serve(request: IncomingMessage, response: ServerResponse): void {
    const url = new URL(request.url ?? "/", this.url);
    const of = matched(url.pathname);
    if (of === null) {
      response.writeHead(404).end();
      return;
    }
    const after = Number(request.headers["last-event-id"] ?? url.searchParams.get("after") ?? 0);
    const mine = this.entries.filter((entry) => entry.seq > after && of(entry));
    if ((request.headers.accept ?? "").includes("text/event-stream")) {
      this.#attach(response, mine, after);
      return;
    }
    // A call's log is live until call.ended; an agent's never ends. `next`: last seq sent, else `after` while live.
    const live = !this.entries.some((entry) => of(entry) && entry.type === "call.ended");
    const last = mine.at(-1);
    const next = last !== undefined ? last.seq : live ? after : null;
    response.writeHead(200, { "content-type": "application/json" }).end(JSON.stringify({ entries: mine, live, next }));
  }

  #attach(response: ServerResponse, replay: Entry[], after: number): void {
    response.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache", connection: "keep-alive" });
    const reader: Reader = { after, response };
    for (const entry of replay) {
      this.#push(reader, entry);
    }
    this.#readers.add(reader);
    // No `error` listener needed: Node drops errors on a destroyed ServerResponse, so only `close` fires.
    response.on("close", () => this.#readers.delete(reader));
  }

  #push(reader: Reader, entry: Entry): void {
    if (entry.seq <= reader.after) {
      return;
    }
    reader.after = entry.seq;
    reader.response.write(`id: ${entry.seq}\ndata: ${JSON.stringify(entry)}\n\n`);
  }
}

/** Entry filter for a path, or null when the path is not a log endpoint. */
function matched(pathname: string): ((entry: Entry) => boolean) | null {
  const call = /^\/v1\/calls\/([^/]+)\/events$/.exec(pathname);
  if (call !== null) {
    return (entry) => entry.call === decodeURIComponent(call[1] as string);
  }
  const agent = /^\/v1\/agents\/([^/]+)\/calls$/.exec(pathname);
  if (agent !== null) {
    return (entry) => entry.agent === decodeURIComponent(agent[1] as string);
  }
  return null;
}
