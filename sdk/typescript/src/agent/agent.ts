/** The Agent base class: its fields are the state, and every assignment is a change with an author. */

// Circular with tools.ts; safe because both sides only call across at runtime (hoisted functions).
import { currentAuthor, UnauthoredWrite } from "./authors.js";
import { docOf, toolsOf, visibleToolsOf, type ToolSpec } from "./tools.js";
import type { Child } from "../views/jsx-runtime.js";
import type { AgentConfig } from "../wire/agent-config.js";
import type { Camel } from "../wire/codec.js";
import type { CallWorld } from "../call/call.js";
import type { Knowledge } from "./knowledge.js";
import type { Ending, Opening } from "./opening.js";
import type { EventDeclarations, EventMeta } from "./accepts.js";
import { declaredStateOf, type Visibility } from "./visibility.js";
import type { Call, MemoryOp } from "./lifecycle.js";
import { collapse, restore, snapshot, type LastCall, type Snapshot } from "./state.js";

type Declared = Camel<AgentConfig>;

// Fields that configure the agent instead of holding state: never diffed, never snapshotted.
// The environment (voice, models, language, opening, memory) is declared on the class, static or
// by decorator, and refused as an instance field.
export const CONFIG_FIELDS = ["phone", "whatsapp", "web", "channelRules"] as const;

// state.ts derives `ConfigName` from CONFIG_FIELDS, so a name added here is dropped from snapshots.
const CONFIG = new Set<string>(CONFIG_FIELDS);

/** One field assignment, as the log and the console read it. */
export interface Change {
  seq: number;
  field: string;
  prev: unknown;
  next: unknown;
  author: string;
  at: number;
}

export type ChangeListener = (change: Change) => void;

/** A named entry the agent wrote to the call's log. */
export interface LogEntry {
  seq: number;
  name: string;
  data?: unknown;
  at: number;
}

export type LogListener = (entry: LogEntry) => void;

/** An external event, as in-process observers receive it after the hook. */
export interface EventHeard {
  name: string;
  data: Record<string, unknown>;
  meta: EventMeta;
}

export type EventListener = (heard: EventHeard) => void;

/** Per-agent framework state, kept off the instance's own fields. */
export interface Internals {
  changes: Change[];
  log: LogEntry[];
  logListeners: Set<LogListener>;
  listeners: Set<ChangeListener>;
  eventListeners: Set<EventListener>;
  seq: number;
  sealed: boolean;
  target: object;
  /** Set by the bridge at start(), never by the app. */
  call: CallWorld | null;
  /** Source for `last(contact)`, from `mount({ last })`. */
  last: LastCall | null;
  /** Facts memory recalled for this call, read by `remembers(text)`. */
  recalled: string[];
}

const internals = new WeakMap<object, Internals>();

/**
 * Base class for every agent. The constructor returns a Proxy, so `this.patient = row` records
 * a change with its author and sequence number.
 */
export class Agent {
  constructor() {
    // null: no `@state` decorators, so every own field is state.
    const stateFields = declaredStateOf(this.constructor);
    const own: Internals = {
      changes: [],
      log: [],
      logListeners: new Set(),
      listeners: new Set(),
      eventListeners: new Set(),
      seq: 0,
      sealed: false,
      target: this,
      call: null,
      last: null,
      recalled: [],
    };
    const proxy = new Proxy(this, {
      set(target, key, next, receiver) {
        // Config fields and undeclared fields (when the class uses `@state`) are not recorded.
        if (typeof key !== "string" || CONFIG.has(key) || (stateFields !== null && !stateFields.has(key))) {
          return Reflect.set(target, key, next, target);
        }
        const prev = Reflect.get(target, key, target) as unknown;
        const ok = Reflect.set(target, key, next, target);
        if (!ok || !own.sealed) return ok;
        const author = currentAuthor();
        // Field initializers run before seal(), so an unauthored write here is a live bug.
        if (author === null) throw new UnauthoredWrite(key);
        if (Object.is(prev, next)) return true;
        const change: Change = { seq: ++own.seq, field: key, prev, next, author, at: Date.now() };
        own.changes.push(change);
        for (const listener of own.listeners) listener(change);
        return true;
      },
    }) as this;
    internals.set(this, own);
    internals.set(proxy, own);
    return proxy;
  }

  /** The class description, as an alternative to a JSDoc comment. */
  static doc?: string;

  /**
   * `false` leaves the `<channel>` block out of the prompt: how to write for a voice, a website's
   * chat or WhatsApp. A config field, never state.
   */
  declare channelRules?: boolean;

  /**
   * Knowledge bases attached to this agent (`pinecall docs attach`), searched from a tool:
   * `await this.knowledge.search("horarios", { k: 3 })`. The gateway runs and logs the search.
   */
  get knowledge(): Knowledge {
    // Async so that a missing call rejects the promise instead of throwing.
    return { search: async (query, options) => await this.call.search(query, options) };
  }

  /** External events this class accepts, and from whom. */
  static events?: EventDeclarations;

  /** Field visibility as a map, as an alternative to `@state`. */
  static visibility?: Record<string, Visibility>;

  // The environment the class may declare: each one declared wins over the agent's settings, and
  // the console shows it set by the class. `voice`, `llm`, `stt` and `judge` are what @voice, @llm,
  // @stt and @judge set.
  /** The language the agent speaks and expects, a BCP 47 tag: `"es"`, `"pt-BR"`. */
  static language?: Declared["language"];
  static voice?: Declared["voice"];
  static llm?: Declared["llm"];
  static stt?: Declared["stt"];
  /** The model the agent's calls are judged on. */
  static judge?: Declared["judge"];
  /** How a call opens: the words, as a string, or `improvise` for the model's own. */
  static greeting?: Opening;
  /** When the model may end the call: in your words, or `true` whenever it judges it done. */
  static hangup?: Ending;
  static turn?: Declared["turn"];
  /** How the voice says a word: `[{ word: "GSA", spoken: "G S A" }]`. */
  static says?: Declared["says"];
  /** Words the ears must know. */
  static hears?: Declared["hears"];
  /** Markdown read whole into every call: `{ path, text }`. */
  static knowledge?: Declared["knowledge"];
  /** The knowledge base searched: `{ base: "clinica", k: 4 }`. */
  static docs?: Declared["docs"];
  /** What memory keeps of a contact and never keeps: `{ remember: […], forget: […] }`. */
  static memory?: Declared["memory"];
  /** Whether the calls keep their audio. */
  static record?: Declared["record"];

  /** The class docstring, as the model reads it. */
  doc(): string | undefined {
    return docOf(this);
  }

  /**
   * The per-turn part of the prompt, rendered from the current state. It is the dynamic block and
   * the last thing the model reads. Renders nothing by default.
   */
  render(): Child {
    return null;
  }

  /**
   * Whether memory recalled a fact for this call containing `text` (the fact or its key word).
   * Returns false until the runtime has recalled anything.
   */
  remembers(text: string): boolean {
    const wanted = text.trim().toLowerCase();
    if (wanted === "") return false;
    return internalsOf(this).recalled.some((known) => known.includes(wanted));
  }

  /** Every tool this agent declares, whether or not the current state shows it. */
  tools(): ToolSpec[] {
    return toolsOf(this).map((declared) => declared.spec);
  }

  /** The tools a model may call right now: the ones whose `when(state)` holds. */
  visibleTools(): ToolSpec[] {
    return visibleToolsOf(this).map((declared) => declared.spec);
  }

  /** Replace the change log with a one-sentence summary; the state is kept. */
  collapse(summary: string): void {
    collapse(this, summary);
  }

  /** Restore the whole state from a snapshot, e.g. in `onCall` for a returning caller. */
  restore(state: Snapshot): void {
    restore(this, state);
  }

  /**
   * Overwrite only the fields `state` names, keeping the rest. Unlike `restore`, which replaces the
   * whole state and clears fields the snapshot omits.
   */
  startIn(state: Snapshot): void {
    restore(this, { ...snapshot(this), ...state });
  }

  /** The snapshot this contact's last call left. Requires `mount(Class, { pc, last })`. */
  last(contact: string): Promise<Snapshot | null> {
    const source = internalsOf(this).last;
    if (source === null) {
      return Promise.reject(
        new Error("last(contact) needs a store: mount the agent with { last } to give it one"),
      );
    }
    return source(contact);
  }

  /** Append a named entry to the call's log. */
  log(name: string, data?: unknown): void {
    const own = internalsOf(this);
    const entry: LogEntry = { seq: ++own.seq, name, at: Date.now() };
    if (data !== undefined) entry.data = data;
    own.log.push(entry);
    for (const listener of own.logListeners) listener(entry);
  }

  /**
   * The call being served. A getter, not a field, so it never enters a snapshot; a subclass field
   * named `call` is refused at its first write. Throws when no call is being served.
   */
  get call(): CallWorld {
    const serving = internalsOf(this).call;
    if (serving === null) {
      throw new Error(
        "this.call is only there while a call is being served: the bridge sets it at start(), " +
          "and a test that renders gives one with setCall(agent, new CallWorld(line, () => {}))",
      );
    }
    return serving;
  }

  /** Speak `text` verbatim now. Resolves true once the turn is delivered. */
  say(text: string, options: { allowInterruptions?: boolean } = {}): Promise<boolean> {
    return this.call.say(text, options);
  }

  /** Make the model speak now, guided by instructions the caller does not hear. Resolves like `say`. */
  reply(instructions: string, options: { allowInterruptions?: boolean } = {}): Promise<boolean> {
    return this.call.reply(instructions, options);
  }

  /** Subscribe in-process to state changes or events. Returns an unsubscribe function. */
  on(type: "state", listener: ChangeListener): () => void;
  on(type: "event", listener: EventListener): () => void;
  on(type: "state" | "event", listener: ChangeListener | EventListener): () => void {
    if (type === "state") return onChange(this, listener as ChangeListener);
    const own = internalsOf(this);
    own.eventListeners.add(listener as EventListener);
    return () => own.eventListeners.delete(listener as EventListener);
  }

  /** Called when a declared external event arrives. State writes here are authored by the event. */
  onEvent(_name: string, _data: Record<string, unknown>, _meta: EventMeta): unknown {
    return undefined;
  }

  /** Called when a call starts. State writes here are authored by the hook. */
  onCall(_call: Call): unknown {
    return undefined;
  }

  /** Called when the call ends. */
  onEnd(_call: Call): unknown {
    return undefined;
  }

  /** Called when memory is written; override to persist the ops. */
  onMemory(_ops: MemoryOp[], _call: Call): unknown {
    return undefined;
  }
}

/** The framework's bookkeeping for an agent; throws if `agent` is not one. */
export function internalsOf(agent: object): Internals {
  const own = internals.get(agent);
  if (!own) throw new TypeError("not a Pinecall agent: its constructor never ran through Agent");
  return own;
}

/** Start recording changes. Assignments before this (field initializers) are the baseline. */
export function seal<T extends object>(agent: T): T {
  internalsOf(agent).sealed = true;
  return agent;
}

/** Every change this agent has recorded, oldest first. */
export function changes(agent: object): readonly Change[] {
  return internalsOf(agent).changes;
}

/** Listen to field assignments. Returns an unsubscribe function. */
export function onChange(agent: object, listener: ChangeListener): () => void {
  const own = internalsOf(agent);
  own.listeners.add(listener);
  return () => own.listeners.delete(listener);
}

/** Everything this agent logged, oldest first. */
export function logOf(agent: object): readonly LogEntry[] {
  return internalsOf(agent).log;
}

/** Listen to log entries. Returns an unsubscribe function. */
export function onLog(agent: object, listener: LogListener): () => void {
  const own = internalsOf(agent);
  own.logListeners.add(listener);
  return () => own.logListeners.delete(listener);
}

/** Whether a name is one of CONFIG_FIELDS rather than a piece of state. */
export function isConfigField(name: string): boolean {
  return CONFIG.has(name);
}

/** Set the store `last(contact)` reads. Called by the bridge at start(). */
export function setLast(agent: object, source: LastCall | null): void {
  internalsOf(agent).last = source;
}

/** Set the call being served. Called by the bridge at start(). */
export function setCall(agent: object, call: CallWorld | null): void {
  internalsOf(agent).call = call;
}

/** Record recalled facts and their key words, from the call's `memory.ops` entries. */
export function recalled(agent: object, words: readonly string[]): void {
  const own = internalsOf(agent);
  for (const word of words) {
    const known = word.trim().toLowerCase();
    if (known !== "" && !own.recalled.includes(known)) own.recalled.push(known);
  }
}

/** Notify in-process observers of an event after its hook ran. */
export function emitEvent(agent: object, heard: EventHeard): void {
  for (const listener of internalsOf(agent).eventListeners) listener(heard);
}
