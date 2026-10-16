// One agent an app serves: its declaration, its tool handlers and its listeners.

import { type AgentConfig } from "../wire/agent-config.js";
import { type Camel, type CommandData, eventOf } from "../wire/codec.js";
import { type DevVerb, type Route, type ToolSpec } from "../wire/defs.js";
import { type Entry } from "../wire/envelope.js";
import { type CommandType, type EventType } from "../wire/registry.js";
import { Call, CallBook, type CallGateway } from "./calls.js";
import { DevRefused, PinecallError, Refused } from "./frames.js";
import { Listeners, asError, camelEvent, type AnyListener, type CamelEvent, type Listener, type Payload } from "./listeners.js";

/** A tool: the spec the model sees and the function that runs when it is called. */
export interface Tool extends Camel<ToolSpec> {
  run: (args: Record<string, unknown>, call: Call) => unknown;
}

/** An agent's declaration plus its tools' code. */
export interface AgentOptions extends Omit<Camel<AgentConfig>, "tools"> {
  tools?: Tool[];
  /**
   * Whether the gateway may route calls that name no app (phone calls, most web calls) to this
   * socket. Defaults to true; a console such as `pinecall chat` passes false.
   */
  takesUnclaimed?: boolean;
  /**
   * Whether this socket answers the console's dev verbs for the agent, beside the process serving
   * its calls. Such a socket declares nothing: it never sends `agent.configure`.
   */
  answersDev?: boolean;
}

/** The client-side socket an agent sends frames through. */
export interface AgentGateway {
  send<K extends CommandType>(type: K, agent: string, call: string | null, data: Camel<CommandData<K>>, id: string): void;
  seen(event: CamelEvent, call: Call | null): void;
  onError(error: Error): void;
  readonly sdk: string;
  readonly host: string;
}

const ANSWER_MS = 10_000;

/**
 * Handles a console's `dev.request`. Resolve with the answer, or throw `DevRefused` to refuse with
 * a status; any other error reaches the console as a 500.
 */
export type DevHandler = (verb: DevVerb, data: Record<string, unknown>) => Promise<Record<string, unknown>>;

const NO_DEV_HANDLER = "this process answers no dev verbs: it is not a `pinecall start` in the agent's directory";

type Waiter = { type: EventType; id: string; settle: (data: unknown) => void; refuse: (error: Error) => void };

/**
 * An agent, from the app's side.
 *
 * The gateway's registry is in memory, so the declaration is re-sent on every reconnect. Several
 * sockets may hold one agent; unclaimed calls go to the newest one that takes them, so a rolling
 * deploy serves as soon as the new process registers. Call `drain()` before exiting to hand live
 * calls over instead of cutting them.
 */
export class Agent implements CallGateway {
  readonly calls: CallBook;
  readonly #listeners: Listeners<Call | null>;
  readonly #tools = new Map<string, Tool>();
  readonly #waiters: Waiter[] = [];
  // Tool runs whose tool.result is not yet sent; a drain waits for these.
  readonly #running = new Set<Promise<void>>();
  #config: Camel<AgentConfig>;
  #takesUnclaimed: boolean;
  #answersDev: boolean;
  #app: string | undefined;
  #dev: DevHandler | undefined;

  constructor(
    readonly slug: string,
    options: AgentOptions,
    private readonly gateway: AgentGateway,
  ) {
    const { tools = [], takesUnclaimed = true, answersDev = false, ...config } = options;
    this.#config = config;
    this.#takesUnclaimed = takesUnclaimed;
    this.#answersDev = answersDev;
    this.declare(tools);
    this.calls = new CallBook(this);
    this.#listeners = new Listeners<Call | null>((error) => gateway.onError(error));
  }

  /** The agent's current declaration, in wire shape. */
  get config(): Camel<AgentConfig> {
    return this.#config;
  }

  /**
   * This socket's app id as minted by the gateway, or undefined before the first register. A call
   * that names it (`WS /v1/chat?app=<id>`, `app` in `POST /v1/calls`) is served by this process.
   */
  get app(): string | undefined {
    return this.#app;
  }

  /** Listen for one event type across every call of this agent. `null` for the agent's own log. */
  on<K extends EventType>(type: K, listener: Listener<K, Call | null>): () => void {
    return this.#listeners.on(type, listener);
  }

  /** Listen for every event of this agent. The returned function stops listening. */
  onAny(listener: AnyListener<Call | null>): () => void {
    return this.#listeners.onAny(listener);
  }

  /**
   * Handle `dev.request` asks relayed from a console. `pinecall start` registers one; without it
   * every ask is refused with 501.
   */
  onDev(handler: DevHandler): void {
    this.#dev = handler;
  }

  /** Replace the tools. The next `configure` sends the new declaration. */
  declare(tools: Tool[]): void {
    this.#tools.clear();
    for (const tool of tools) {
      this.#tools.set(tool.name, tool);
    }
    this.#config = { ...this.#config, tools: tools.map(({ run: _run, ...spec }) => spec) };
  }

  /** Update the declaration. Only the given fields change; live calls keep their session. */
  async configure(changes: Partial<Camel<AgentConfig>> = {}): Promise<Payload<"agent.configured">> {
    this.#config = { ...this.#config, ...changes };
    return this.#ask("agent.configure", "agent.configured", { config: this.#config });
  }

  /** Register the slug, then send the declaration. Runs again on every reconnect. */
  async open(): Promise<void> {
    // Routes are org rows now; the empty field stays for older gateways.
    const registered = await this.#ask("agent.register", "agent.registered", {
      routes: [],
      sdk: this.gateway.sdk,
      host: this.gateway.host,
      takesUnclaimed: this.#takesUnclaimed,
      ...(this.#answersDev ? { answersDev: true } : {}),
    });
    // Each reconnect mints a new app id.
    this.#app = registered.app;
    // A registration inherits the newest holder's declaration; one sent from here would replace it.
    if (!this.#answersDev) await this.configure();
  }

  // ── the socket's side ───────────────────────────────────────────────────────

  /** Fold one entry into its call and dispatch it to listeners. */
  take(entry: Entry): void {
    const event = camelEvent(eventOf(entry));
    const call = entry.call === null ? null : this.calls.of(entry.call, entry.ts);
    this.#settle(event);
    call?.take(event);
    this.#listeners.emit(event, call);
    this.gateway.seen(event, call);
    if (event.type === "dev.request") {
      this.#onDevRequest(event.data);
      return;
    }
    if (call !== null) {
      this.#onToolCall(event, call);
      this.calls.forget(call);
    }
  }

  /** Send one command on this agent's behalf. */
  command<K extends CommandType>(type: K, call: string | null, data: Camel<CommandData<K>>): void {
    this.gateway.send(type, this.slug, call, data, `${this.slug}:${type}`);
  }

  /** Report an error no caller is waiting on. */
  onError(error: Error): void {
    this.gateway.onError(error);
  }

  /**
   * Stop receiving new calls and hand live ones to another holder (or park them for the next).
   * Running tools still answer. Resolves with where the calls went.
   */
  async drain(answerMs = ANSWER_MS): Promise<Payload<"agent.draining">> {
    return this.#ask("agent.drain", "agent.draining", {}, answerMs);
  }

  /** Number of tool runs in progress. */
  get inFlight(): number {
    return this.#running.size;
  }

  /** Resolve once every running tool has sent its tool.result. */
  async settled(): Promise<void> {
    await Promise.all([...this.#running]);
  }

  /** Send `ping`; the gateway answers with `pong`. */
  ping(): void {
    this.command("ping", null, {});
  }

  // ── tools ───────────────────────────────────────────────────────────────────

  // Every outcome must produce exactly one tool.result: a turn without one waits forever.
  #onToolCall(event: CamelEvent, call: Call): void {
    if (event.type !== "tool.call") {
      return;
    }
    const { callId, name, arguments: args } = event.data;
    const tool = this.#tools.get(name);
    if (tool === undefined) {
      call.toolResult({ callId, name, error: `this app declares no tool called ${name}` });
      return;
    }
    const started = Date.now();
    const running = (async () => {
      try {
        const output = await tool.run(args, call);
        call.toolResult({ callId, name, output, durationS: (Date.now() - started) / 1000 });
      } catch (failed) {
        // A rejection is the tool's answer (sent as `error`), not an app failure; don't report it.
        const error = asError(failed);
        try {
          call.toolResult({ callId, name, error: error.message, durationS: (Date.now() - started) / 1000 });
        } catch (unsent) {
          this.onError(asError(unsent));
        }
      }
    })();
    this.#running.add(running);
    void running.finally(() => this.#running.delete(running));
  }

  // ── a console's ask ─────────────────────────────────────────────────────────

  // Every outcome must produce one dev.answer, or the console's request hangs until timeout.
  #onDevRequest(asked: Payload<"dev.request">): void {
    const { id, verb, data } = asked;
    void (async () => {
      try {
        if (this.#dev === undefined) throw new DevRefused(501, NO_DEV_HANDLER);
        const result = await this.#dev(verb, data);
        this.command("dev.answer", null, { id, result });
      } catch (failed) {
        const refused =
          failed instanceof DevRefused
            ? { status: failed.status, detail: failed.detail }
            : { status: 500, detail: asError(failed).message };
        this.command("dev.answer", null, { id, refused });
      }
    })();
  }

  // ── waiting for an answer ───────────────────────────────────────────────────

  // Resolved by the event the command lands as, or rejected by an `error` carrying our id.
  async #ask<K extends CommandType, E extends EventType>(
    type: K,
    lands: E,
    data: Camel<CommandData<K>>,
    withinMs = ANSWER_MS,
  ): Promise<Payload<E>> {
    const id = `${this.slug}:${type}`;
    const answer = new Promise<Payload<E>>((resolve, reject) => {
      const waiter: Waiter = { type: lands, id, settle: (payload) => resolve(payload as Payload<E>), refuse: reject };
      this.#waiters.push(waiter);
      setTimeout(() => {
        this.#drop(waiter);
        reject(new PinecallError(`${type}: the gateway did not answer in ${withinMs}ms`));
      }, withinMs).unref();
    });
    this.gateway.send(type, this.slug, null, data, id);
    return answer;
  }

  #settle(event: CamelEvent): void {
    for (const waiter of [...this.#waiters]) {
      if (event.type === waiter.type) {
        this.#drop(waiter);
        waiter.settle(event.data);
      } else if (event.type === "error" && event.data.id === waiter.id) {
        this.#drop(waiter);
        waiter.refuse(new Refused(event.data));
      }
    }
  }

  #drop(waiter: Waiter): void {
    const at = this.#waiters.indexOf(waiter);
    if (at !== -1) {
      this.#waiters.splice(at, 1);
    }
  }
}
