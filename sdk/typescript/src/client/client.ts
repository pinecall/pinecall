// The client: one socket, the agents registered on it, and log reads for the key's org.

import { createRequire } from "node:module";
import { hostname } from "node:os";
import { type Camel, type CommandData, eventOf } from "../wire/codec.js";
import { type Entry } from "../wire/envelope.js";
import { type CommandType, type EventType } from "../wire/registry.js";
import { Agent, type AgentGateway, type AgentOptions } from "./agent.js";
import type { Call } from "./calls.js";
import { Connection, type Backoff, type ConnectionOptions } from "./connection.js";
import { lookupUrl } from "./endpoints.js";
import { PinecallError, frame } from "./frames.js";
import { Listeners, asError, type AnyListener, type CamelEvent, type Listener } from "./listeners.js";
import { history, observe, type LogTarget, type Observation, type Page, type ReadOptions } from "./observe.js";
import { signed, type World } from "./signed.js";

// Two levels up from both dist/client/ and src/client/.
const { version } = createRequire(import.meta.url)("../../package.json") as { version: string };

// `error` code sent when an org member stops this app (`POST /v1/apps/{app}/stop`). The client must
// not reconnect afterwards, or the stop would have no effect.
const STOPPED = "stopped";

/** A search result chunk: its source path, heading and text. */
export interface Found {
  path: string;
  heading: string | null;
  text: string;
}

/** Timeouts for `drain()`: the gateway's answer per agent, and running tools. */
export interface DrainOptions {
  answerMs?: number;
  toolsMs?: number;
}

/** Result of `drain()`: calls handed over, calls parked, tools running and tools that finished. */
export interface Drained {
  handed: number;
  parked: number;
  tools: number;
  finished: number;
}

// Should fit inside the process manager's shutdown grace period.
const DEFAULT_TOOLS_MS = 30_000;

/** Options for `new Pinecall()`. `url` and `apiKey` are required. */
export interface PinecallOptions {
  url?: string;
  apiKey?: string;
  /**
   * The world this client expects, sent on every request; a gateway of the other world refuses
   * it. Required for a person's key on production; not needed for a server token.
   */
  env?: World;
  /** How this app names itself in the org's list of processes; `pinecall/<version>` otherwise. */
  sdk?: string;
  pingMs?: number;
  backoff?: Partial<Backoff>;
}

/**
 * One app's connection to Pinecall.
 *
 * `url` and `apiKey` must be passed explicitly; nothing is read from the environment, so a stale
 * `PINECALL_API_KEY` (also used by the v1 SDK) can never select the wrong org.
 */
export class Pinecall implements AgentGateway {
  readonly sdk: string;
  /** This machine's hostname, shown by the gateway next to the app. */
  readonly host = hostname();
  /** The gateway this client talks to. */
  readonly url: string;
  /** The API key. Sent in a header, never in a URL. */
  readonly apiKey: string;
  /** The requested world, or undefined to use the key's own. */
  readonly env: World | undefined;
  readonly #agents = new Map<string, Agent>();
  readonly #listeners: Listeners<Call | null>;
  readonly #errors = new Set<(error: Error) => void>();
  readonly #connects = new Set<() => void>();
  readonly #stops = new Set<(why: string) => void>();
  readonly #entries = new Set<(entry: Entry) => void>();
  readonly #connection: Connection;

  constructor(options: PinecallOptions = {}) {
    const { url, apiKey } = options;
    if (url === undefined || apiKey === undefined) {
      throw new PinecallError("new Pinecall({ url, apiKey }): one of the two was not given");
    }
    this.url = url;
    this.apiKey = apiKey;
    this.env = options.env;
    this.sdk = options.sdk ?? `pinecall/${version}`;
    this.#listeners = new Listeners<Call | null>((error) => this.onError(error));
    const dial: ConnectionOptions = { url, apiKey, ...(options.env === undefined ? {} : { env: options.env }) };
    if (options.pingMs !== undefined) {
      dial.pingMs = options.pingMs;
    }
    if (options.backoff !== undefined) {
      dial.backoff = options.backoff;
    }
    this.#connection = new Connection(dial, {
      onOpen: () => this.#declareAll(),
      onEntry: (entry) => this.#take(entry),
      onError: (error) => this.onError(error),
      onHeartbeat: () => this.#pingAll(),
    });
  }

  /** Declare an agent this app serves. Nothing is sent until `connect`. */
  agent(slug: string, options: AgentOptions = {}): Agent {
    const agent = new Agent(slug, options, this);
    this.#agents.set(slug, agent);
    return agent;
  }

  /** Open the socket, register every agent and send its declaration. */
  async connect(): Promise<void> {
    await this.#connection.start();
  }

  /**
   * Shut down without cutting calls: each agent drains (live calls move to another holder or are
   * parked) and running tools get up to `toolsMs` to finish. Does not close the socket; call
   * `close()` afterwards.
   */
  async drain({ answerMs, toolsMs = DEFAULT_TOOLS_MS }: DrainOptions = {}): Promise<Drained> {
    this.#connection.leaving();
    const agents = [...this.#agents.values()];
    const done: Drained = { handed: 0, parked: 0, tools: 0, finished: 0 };
    if (!this.connected) return done;
    const answers = await Promise.allSettled(agents.map((agent) => agent.drain(answerMs)));
    for (const answer of answers) {
      if (answer.status === "fulfilled") {
        done.handed += answer.value.handed;
        done.parked += answer.value.parked;
      } else {
        this.onError(asError(answer.reason));
      }
    }
    done.tools = agents.reduce((sum, agent) => sum + agent.inFlight, 0);
    let timer: NodeJS.Timeout | undefined;
    const cap = new Promise<void>((resolve) => {
      timer = setTimeout(resolve, toolsMs);
    });
    await Promise.race([Promise.all(agents.map((agent) => agent.settled())), cap]);
    clearTimeout(timer);
    done.finished = done.tools - agents.reduce((sum, agent) => sum + agent.inFlight, 0);
    return done;
  }

  /** Close the socket without reconnecting. Every agent's slug is released. */
  close(): void {
    this.#connection.close();
  }

  /** True while the socket is up. */
  get connected(): boolean {
    return this.#connection.open;
  }

  /** Listen for one event type across every agent on this client. */
  on<K extends EventType>(type: K, listener: Listener<K, Call | null>): () => void {
    return this.#listeners.on(type, listener);
  }

  /** Listen for every event across every agent. */
  onAny(listener: AnyListener<Call | null>): () => void {
    return this.#listeners.onAny(listener);
  }

  /**
   * Called after each (re)connect once every agent is declared. Use it to re-send state the
   * gateway keeps only for a live socket.
   */
  onConnected(listener: () => void): () => void {
    this.#connects.add(listener);
    return () => {
      this.#connects.delete(listener);
    };
  }

  /**
   * Called when an org member stops this app. The socket is closed for good; the app decides what
   * to do next (usually exit).
   */
  onStopped(listener: (why: string) => void): () => void {
    this.#stops.add(listener);
    return () => {
      this.#stops.delete(listener);
    };
  }

  /**
   * Every entry the socket receives, as the gateway wrote it (snake_case), before any agent takes
   * it — other agents' entries and the client's own errors included.
   */
  onEntries(listener: (entry: Entry) => void): () => void {
    this.#entries.add(listener);
    return () => {
      this.#entries.delete(listener);
    };
  }

  /** Receive errors no caller awaits (bad frames, listener throws, socket loss). Defaults to `console.error`. */
  onErrors(listener: (error: Error) => void): () => void {
    this.#errors.add(listener);
    return () => {
      this.#errors.delete(listener);
    };
  }

  /** Stream a log live, folded by the protocol's reducer. */
  observe(target: LogTarget, options: Partial<ReadOptions> = {}): AsyncGenerator<Observation> {
    return observe(target, this.#reading(options));
  }

  /** Read one page of a log and its folded state. */
  async history(target: LogTarget, options: Partial<ReadOptions> = {}): Promise<Page> {
    return history(target, this.#reading(options));
  }

  /**
   * Search the agent's knowledge bases on behalf of a call this client serves. The gateway runs
   * the search and logs it.
   * @param k Number of chunks; defaults to the base's setting.
   */
  async search(call: string, query: string, k?: number): Promise<Found[]> {
    const answered = await fetch(lookupUrl(this.url, call), {
      method: "POST",
      headers: { ...signed(this.apiKey, this.env), "content-type": "application/json" },
      body: JSON.stringify({ tool: "search", input: k === undefined ? { query } : { query, k } }),
    });
    const text = await answered.text();
    if (!answered.ok) throw new PinecallError(`search: the gateway answered ${answered.status}: ${detailOf(text)}`);
    return (JSON.parse(text) as { output: { chunks: Found[] } }).output.chunks;
  }

  // ── what the agents send through ────────────────────────────────────────────

  /** Send one command frame, validated against its schema. */
  send<K extends CommandType>(type: K, agent: string, call: string | null, data: Camel<CommandData<K>>, id: string): void {
    this.#connection.send(frame(type, agent, call, data, id));
  }

  /** Emit an event an agent has handled to the client-wide listeners. */
  seen(event: CamelEvent, call: Call | null): void {
    this.#listeners.emit(event, call);
  }

  /** Report an error no caller awaits. */
  onError(error: Error): void {
    if (this.#errors.size === 0) {
      console.error(error);
      return;
    }
    for (const listener of this.#errors) {
      listener(error);
    }
  }

  #take(entry: Entry): void {
    for (const listener of this.#entries) {
      try {
        listener(entry);
      } catch (failed) {
        this.onError(asError(failed));
      }
    }
    if (entry.type === "error" && entry.agent === "") {
      const said = eventOf(entry);
      if (said.type === "error" && said.data.code === STOPPED) return this.#stopped(said.data.message);
    }
    const agent = this.#agents.get(entry.agent);
    if (agent === undefined) {
      // Not one of ours: the socket may carry other agents' entries.
      return;
    }
    try {
      agent.take(entry);
    } catch (failed) {
      this.onError(asError(failed));
    }
  }

  // With no stop listener, report the stop as an error so it is not silent.
  #stopped(why: string): void {
    this.#connection.close();
    if (this.#stops.size === 0) {
      this.onError(new PinecallError(why));
      return;
    }
    for (const listener of this.#stops) {
      try {
        listener(why);
      } catch (failed) {
        this.onError(asError(failed));
      }
    }
  }

  async #declareAll(): Promise<void> {
    for (const agent of this.#agents.values()) {
      await agent.open();
    }
    for (const listener of this.#connects) {
      try {
        listener();
      } catch (failed) {
        this.onError(asError(failed));
      }
    }
  }

  #pingAll(): void {
    for (const agent of this.#agents.values()) {
      try {
        agent.ping();
      } catch (failed) {
        this.onError(asError(failed));
      }
    }
  }

  #reading(options: Partial<ReadOptions>): ReadOptions {
    return { url: this.url, apiKey: this.apiKey, ...(this.env === undefined ? {} : { env: this.env }), ...options };
  }
}

/** The `detail` of an error body, or the raw body. */
function detailOf(text: string): string {
  try {
    const parsed = JSON.parse(text) as { detail?: unknown };
    return typeof parsed.detail === "string" ? parsed.detail : text;
  } catch {
    return text;
  }
}
