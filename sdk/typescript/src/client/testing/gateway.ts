// An in-process fake gateway: enough of the app socket to test an app's agents.

import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";

import { type Command, CommandSchema, type Entry } from "../../wire/envelope.js";
import { EPHEMERAL_EVENTS, type EventType } from "../../wire/registry.js";
import { WebSocket, WebSocketServer } from "ws";

import { LOOPBACK } from "./loopback.js";

// Unknown keys are refused during the handshake, so the upgrade never happens.
const FORBIDDEN = 403;

// Close code for a valid key that lacks the scope for this endpoint.
const POLICY_VIOLATION = 1008;

/** Options for `FakeGateway.start()`. */
export interface FakeGatewayOptions {
  /** The only accepted key; any other fails the handshake with 403. */
  apiKey?: string;
  /** Slugs whose registration is refused, as when another agent or fleet holds them. */
  taken?: string[];
  /** Close every socket with 1008 and this reason, as for a key without the needed scope. */
  refusesWith?: string;
  /** Never answer `agent.drain`, like an older or hung gateway. */
  holdsDrain?: boolean;
}

/** A command the fake gateway received. */
export type Received = Command;

/** A scripted search result chunk. */
export interface Scripted {
  path: string;
  heading: string | null;
  text: string;
}

/** A search request recorded by the fake gateway. */
export interface Searched {
  call: string;
  query: string;
  k: number | undefined;
}

// The only HTTP endpoint: knowledge search, answered with scripted chunks.
const LOOKUP = /^\/v1\/calls\/([^/]+)\/lookup$/;

/**
 * A fake gateway with no sessions, store or model. It numbers entries, answers the commands the
 * app socket handles itself, and lets a test push any entry to connected apps.
 */
export class FakeGateway {
  readonly received: Received[] = [];
  /** Every search made through this gateway, in order. */
  readonly searched: Searched[] = [];
  readonly #http: Server;
  readonly #server: WebSocketServer;
  #found: Scripted[] = [];
  readonly #sockets = new Set<WebSocket>();
  readonly #refused: Set<string>;
  #seq = 0;
  #apps = 0;
  #port = 0;

  private constructor(http: Server, server: WebSocketServer, private readonly options: FakeGatewayOptions) {
    this.#http = http;
    this.#server = server;
    this.#refused = new Set(options.taken ?? []);
  }

  // The key is checked during the handshake, as the real gateway does.
  /** Start on a random port. Close it when the test is over. */
  static async start(options: FakeGatewayOptions = {}): Promise<FakeGateway> {
    // One HTTP server for both the /v1/apps upgrade and the search endpoint.
    const http = createServer((request, response) => void gateway.#answerHttp(request, response));
    const server = new WebSocketServer({
      server: http,
      path: "/v1/apps",
      verifyClient: ({ req }, done) => done(options.apiKey === undefined || req.headers.authorization === `Bearer ${options.apiKey}`, FORBIDDEN),
    });
    const gateway = new FakeGateway(http, server, options);
    // Bind to 127.0.0.1 only: the IPv6 wildcard can be granted on a port another program holds
    // on IPv4, and the client's 127.0.0.1 connection would reach that program instead.
    await new Promise<void>((resolve) => http.listen(0, LOOPBACK, resolve));
    const address = http.address();
    gateway.#port = typeof address === "object" && address !== null ? address.port : 0;
    server.on("connection", (socket) => {
      if (options.refusesWith !== undefined) {
        socket.close(POLICY_VIOLATION, options.refusesWith);
        return;
      }
      gateway.#accept(socket);
    });
    return gateway;
  }

  /** The URL to give a client as PINECALL_URL. */
  get url(): string {
    return `http://${LOOPBACK}:${this.#port}`;
  }

  /** How many apps are connected right now. */
  get connections(): number {
    return this.#sockets.size;
  }

  /** Received commands of one type, in arrival order. */
  commandsOf(type: string): Received[] {
    return this.received.filter((command) => command.type === type);
  }

  /** Push one numbered entry to every connected app. */
  emit(agent: string, call: string | null, type: EventType, data: Record<string, unknown>): Entry {
    const entry: Entry = { seq: (this.#seq += 1), ts: Date.now() / 1000, call, agent, type, ephemeral: EPHEMERAL_EVENTS.has(type), data };
    for (const socket of this.#sockets) {
      socket.send(JSON.stringify(entry));
    }
    return entry;
  }

  /** Set the chunks (best first) that subsequent searches return. */
  finds(chunks: Scripted[]): void {
    this.#found = chunks;
  }

  /** Drop every open socket while still listening, simulating a gateway restart. */
  cut(): void {
    for (const socket of this.#sockets) {
      socket.terminate();
    }
    this.#sockets.clear();
  }

  /** Stop every connected app as `POST /v1/apps/{app}/stop` does: an `error` coded `stopped`, then close. */
  stop(why: string): void {
    for (const socket of this.#sockets) {
      socket.send(JSON.stringify(this.#entry("", null, "error", { code: "stopped", message: why, recoverable: false })));
      socket.close();
    }
  }

  /** Stop listening and close all connections. */
  async close(): Promise<void> {
    this.cut();
    await new Promise<void>((resolve, reject) => this.#server.close((failed) => (failed ? reject(failed) : resolve())));
    this.#http.closeAllConnections();
    await new Promise<void>((resolve, reject) => this.#http.close((failed) => (failed ? reject(failed) : resolve())));
  }

  async #answerHttp(request: IncomingMessage, response: ServerResponse): Promise<void> {
    const call = LOOKUP.exec(request.url ?? "")?.[1];
    if (request.method !== "POST" || call === undefined) {
      response.writeHead(404).end();
      return;
    }
    if (this.options.apiKey !== undefined && request.headers.authorization !== `Bearer ${this.options.apiKey}`) {
      response.writeHead(401, { "content-type": "application/json" }).end(JSON.stringify({ detail: "this door takes an API key" }));
      return;
    }
    const chunks: Buffer[] = [];
    for await (const chunk of request) chunks.push(chunk as Buffer);
    const { input } = JSON.parse(Buffer.concat(chunks).toString("utf8")) as { input: { query: string; k?: number } };
    this.searched.push({ call: decodeURIComponent(call), query: input.query, k: input.k });
    const found = input.k === undefined ? this.#found : this.#found.slice(0, input.k);
    response.writeHead(200, { "content-type": "application/json" }).end(JSON.stringify({ output: { chunks: found }, took_ms: 1 }));
  }

  #accept(socket: WebSocket): void {
    this.#sockets.add(socket);
    // Per-connection id, returned in `agent.registered` as the real gateway does.
    const app = `app_${(this.#apps += 1)}`;
    socket.on("message", (raw: Buffer) => this.#take(socket, app, raw));
    socket.on("close", () => this.#sockets.delete(socket));
    // An unhandled `error` event throws in Node; `ws` emits one for any unparseable frame, which
    // would crash the whole test run.
    socket.on("error", () => this.#sockets.delete(socket));
  }

  #take(socket: WebSocket, app: string, raw: Buffer): void {
    const command = CommandSchema.parse(JSON.parse(raw.toString()) as unknown);
    this.received.push(command);
    switch (command.type) {
      case "agent.register":
        return this.#register(socket, app, command);
      case "agent.configure":
        return this.#answer(socket, command, "agent.configured", { changed: Object.keys((command.data["config"] ?? {}) as object) });
      case "ping":
        return this.#answer(socket, command, "pong", { ts: Date.now() / 1000 });
      case "agent.drain":
        if (this.options.holdsDrain === true) return;
        return this.#answer(socket, command, "agent.draining", { app, env: "sandbox", handed: 0, parked: 0 });
      default:
        return;
    }
  }

  // Several sockets may register one agent; only slugs in `taken` are refused.
  #register(socket: WebSocket, app: string, command: Command): void {
    if (this.#refused.has(command.agent)) {
      this.#refuse(socket, command, "refused", `${command.agent} answers at a door somebody else has`);
      return;
    }
    const { routes, sdk } = command.data as { routes: unknown; sdk?: string };
    this.#answer(socket, command, "agent.registered", sdk === undefined ? { routes, app } : { routes, app, sdk });
  }

  #answer(socket: WebSocket, command: Command, type: EventType, data: Record<string, unknown>): void {
    socket.send(JSON.stringify(this.#entry(command.agent, null, type, data)));
  }

  #refuse(socket: WebSocket, command: Command, code: string, message: string): void {
    const data: Record<string, unknown> = { code, message, recoverable: true, command: command.type };
    if (command.id !== undefined) {
      data["id"] = command.id;
    }
    socket.send(JSON.stringify(this.#entry(command.agent, null, "error", data)));
  }

  #entry(agent: string, call: string | null, type: EventType, data: Record<string, unknown>): Entry {
    return { seq: (this.#seq += 1), ts: Date.now() / 1000, call, agent, type, ephemeral: EPHEMERAL_EVENTS.has(type), data };
  }
}
