// A live call as the app holds it: its known fields and the commands it can send.

import { type Camel, type CommandData } from "../wire/codec.js";
import { type Channel, type Contact, type Medium, type ToolResult, type ToolSpec } from "../wire/defs.js";
import { type CommandType, type EventType } from "../wire/registry.js";
import type { AnyListener, CamelEvent, Listener } from "./listeners.js";
import { Listeners } from "./listeners.js";

/** The agent a call sends its commands through. */
export interface CallGateway {
  readonly slug: string;
  command<K extends CommandType>(type: K, call: string | null, data: Camel<CommandData<K>>): void;
  onError(error: Error): void;
}

/** The call's lifecycle status, as reported by the log so far. */
export type CallStatus = "ringing" | "dialing" | "active" | "ended";

/**
 * A call the app is serving.
 *
 * Fields come only from log entries. Each method sends one command without awaiting it; the result
 * arrives later as log events.
 */
export class Call {
  status: CallStatus = "ringing";
  channel: Channel | null = null;
  /** Spoken or written, as `call.started` says; null before it, and from a gateway that does not say. */
  medium: Medium | null = null;
  from: string | null = null;
  to: string | null = null;
  contact: Camel<Contact> | null = null;
  /** The eval run that opened this call, or null for a real caller. */
  run: string | null = null;
  /** The page code this call claimed, or null. */
  claimed: string | null = null;
  /** The app state as last set here or reported by `state.changed`. */
  state: Record<string, unknown> = {};
  /**
   * The day the call opened, `YYYY-MM-DD` in this process's timezone. On `call.attached` it is the
   * original start day, not the handover day.
   */
  today: string;

  readonly #listeners: Listeners<Call>;

  constructor(
    readonly id: string,
    private readonly gateway: CallGateway,
    openedAt: number,
  ) {
    this.today = dayOf(openedAt);
    this.#listeners = new Listeners<Call>((error) => gateway.onError(error));
  }

  /** The agent serving this call. */
  get agent(): string {
    return this.gateway.slug;
  }

  /** Listen for one event type on this call. The returned function stops listening. */
  on<K extends EventType>(type: K, listener: Listener<K, Call>): () => void {
    return this.#listeners.on(type, listener);
  }

  /** Listen for every event on this call. The returned function stops listening. */
  onAny(listener: AnyListener<Call>): () => void {
    return this.#listeners.onAny(listener);
  }

  // ── the commands ────────────────────────────────────────────────────────────

  /** Say this, verbatim, now. Lands as `turn.agent`. */
  say(text: string, options: { allowInterruptions?: boolean } = {}): void {
    this.gateway.command("agent.say", this.id, { text, ...options });
  }

  /** Make the model speak now, following instructions the caller does not hear. Lands as `turn.agent`. */
  reply(instructions: string, options: { allowInterruptions?: boolean } = {}): void {
    this.gateway.command("agent.reply", this.id, { instructions, ...options });
  }

  /** Replace one named prompt block: a built-in one or one the agent declared. */
  setPrompt(name: string, text: string): void {
    this.gateway.command("prompt.set", this.id, { name, text });
  }

  /** Set which declared tools the model may see now. */
  setTools(tools: Camel<ToolSpec>[]): void {
    this.gateway.command("tools.set", this.id, { tools });
  }

  /** Send the full app state. Lands as `state.changed`. */
  setState(state: Record<string, unknown>, changed?: string[]): void {
    this.state = { ...state };
    this.gateway.command("state.set", this.id, changed === undefined ? { state } : { state, changed });
  }

  /** Send a tool's result for the model's `call_id`. */
  toolResult(result: Camel<ToolResult>): void {
    this.gateway.command("tool.result", this.id, result);
  }

  /** Send an event from the tenant's backend. Refused unless the agent declared the name. */
  event(name: string, data: Record<string, unknown>): void {
    this.gateway.command("call.event", this.id, { name, data });
  }

  /** End the call from the app's side. `call.ended` follows with reason agent_hung_up. */
  hangup(reason?: string): void {
    this.gateway.command("call.hangup", this.id, reason === undefined ? {} : { reason });
  }

  /** Bind this call to a page code. Lands as `call.claimed`, or is refused with `no_code`. */
  claim(code: string): void {
    this.gateway.command("call.claim", this.id, { code });
  }

  /** Write an app-defined entry to the call's log. Lands as `custom`. */
  log(name: string, data: Record<string, unknown> = {}): void {
    this.gateway.command("call.log", this.id, { name, data });
  }

  // ── what the log teaches it ─────────────────────────────────────────────────

  /** Apply one event to the call's fields, then emit it to this call's listeners. */
  take(event: CamelEvent): void {
    this.#learn(event);
    this.#listeners.emit(event, this);
  }

  #learn(event: CamelEvent): void {
    switch (event.type) {
      case "call.ringing":
        this.status = "ringing";
        this.#line(event.data);
        return;
      case "call.dialing":
        this.status = "dialing";
        this.#line(event.data);
        return;
      case "call.started":
        this.status = "active";
        this.#line(event.data);
        this.medium = event.data.medium ?? null;
        // A run's call says its day, which a golden may have pinned; a person's runs on the clock's.
        if (event.data.today != null) this.today = event.data.today;
        return;
      case "call.ended":
        this.status = "ended";
        return;
      // Handed over mid-conversation: carries the original start and current state.
      case "call.attached":
        this.status = "active";
        this.#line(event.data.started);
        this.medium = event.data.started.medium ?? null;
        this.state = { ...event.data.state };
        this.today = event.data.started.today ?? dayOf(event.data.started.startedAt);
        // `claimed` is absent from gateways before protocol 0.6.11.
        this.claimed = event.data.claimed ?? null;
        return;
      case "state.changed":
        this.state = { ...event.data.state };
        return;
      case "call.claimed":
        this.claimed = event.data.code;
        return;
      default:
        return;
    }
  }

  #line(line: {
    channel: Channel;
    from: string;
    to: string;
    caller: Camel<Contact> | null;
    run?: string | null | undefined;
  }): void {
    this.channel = line.channel;
    this.from = line.from;
    this.to = line.to;
    this.contact = line.caller;
    this.run = line.run ?? null;
  }
}

/** The calls an agent is serving, by id. A call is dropped once it ends. */
export class CallBook {
  readonly #live = new Map<string, Call>();

  constructor(private readonly gateway: CallGateway) {}

  /** The calls in progress, in the order they opened. */
  get live(): Call[] {
    return [...this.#live.values()];
  }

  /** Return the call with this id, creating it on first sight. */
  of(id: string, at: number): Call {
    const known = this.#live.get(id);
    if (known !== undefined) {
      return known;
    }
    const call = new Call(id, this.gateway, at);
    this.#live.set(id, call);
    return call;
  }

  /** Drop the call if it has ended. Runs after `call.ended` listeners. */
  forget(call: Call): void {
    if (call.status === "ended") {
      this.#live.delete(call.id);
    }
  }
}

/** `YYYY-MM-DD` of a unix timestamp, in local time. */
function dayOf(ts: number): string {
  const at = new Date(ts * 1000);
  const pad = (n: number): string => String(n).padStart(2, "0");
  return `${at.getFullYear()}-${pad(at.getMonth() + 1)}-${pad(at.getDate())}`;
}
