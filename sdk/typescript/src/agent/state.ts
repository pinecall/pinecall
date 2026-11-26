/** Agent state as a plain object: snapshot, diff, restore and collapse. */

import { Agent, CONFIG_FIELDS, changes, internalsOf, isConfigField } from "./agent.js";
import { currentAuthor, withAuthor } from "./authors.js";
import { declaredStateOf } from "./visibility.js";

type ConfigName = (typeof CONFIG_FIELDS)[number];

// Fields and getters, minus methods and config fields.
type StateOf<T> = {
  [K in keyof T as T[K] extends Function ? never : K extends ConfigName ? never : K]: T[K];
};

/**
 * The agent's state as a plain object: no methods, no config fields. `Snapshot<T>` is typed for
 * class `T`; bare `Snapshot` is an untyped record.
 */
export type Snapshot<T = unknown> = unknown extends T ? Record<string, unknown> : StateOf<T>;

/** One field that differs between two snapshots. */
export interface FieldDiff {
  field: string;
  prev: unknown;
  next: unknown;
}

// Own non-function, non-config fields; restricted to `@state` fields when the class declares any.
function isStateField(key: string, value: unknown, declared: ReadonlySet<string> | null): boolean {
  if (isConfigField(key) || typeof value === "function") return false;
  return declared === null || declared.has(key);
}

/** The class's `@state` fields, or null when it declares none. */
function stateOf(agent: object): ReadonlySet<string> | null {
  return declaredStateOf((internalsOf(agent).target as { constructor: Function }).constructor);
}

// Getters are state too (`when` predicates read them). Stop at Agent so framework accessors are excluded.
function gettersOf(agent: object): string[] {
  const names: string[] = [];
  for (
    let prototype: object | null = Object.getPrototypeOf(agent);
    prototype && prototype !== Object.prototype;
    prototype = Object.getPrototypeOf(prototype)
  ) {
    if ((prototype as { constructor?: unknown }).constructor === Agent) break;
    for (const [name, descriptor] of Object.entries(Object.getOwnPropertyDescriptors(prototype))) {
      if (typeof descriptor.get === "function" && !names.includes(name)) names.push(name);
    }
  }
  return names;
}

/** A copy of the agent's current state, including getters. */
export function snapshot(agent: object): Snapshot {
  const own = internalsOf(agent);
  const readable = agent as Record<string, unknown>;
  const declared = stateOf(agent);
  const state: Snapshot = {};
  for (const key of Object.keys(own.target)) {
    const value = (own.target as Record<string, unknown>)[key];
    if (isStateField(key, value, declared)) state[key] = value;
  }
  // Getters read through the proxy, since they are written against `this`.
  for (const name of gettersOf(agent)) state[name] = readable[name];
  return state;
}

/** Fields that differ between two snapshots. */
export function diff(before: Snapshot, after: Snapshot): FieldDiff[] {
  const fields = new Set([...Object.keys(before), ...Object.keys(after)]);
  const changed: FieldDiff[] = [];
  for (const field of fields) {
    if (!Object.is(before[field], after[field])) {
      changed.push({ field, prev: before[field], next: after[field] });
    }
  }
  return changed;
}

/** Replace the agent's state with a snapshot, authored by the current author or `restore`. */
export function restore(agent: object, state: Snapshot): void {
  const author = currentAuthor() ?? "restore";
  const derived = new Set(gettersOf(agent));
  const declared = stateOf(agent);
  const target = internalsOf(agent).target as Record<string, unknown>;
  withAuthor(author, () => {
    const writable = agent as Record<string, unknown>;
    const fields = new Set(Object.keys(target));
    // State fields missing from the snapshot are cleared; non-state fields are left alone.
    for (const key of fields) {
      if (isStateField(key, target[key], declared) && !(key in state)) writable[key] = undefined;
    }
    // Skip getters: they derive from the restored fields.
    for (const [key, value] of Object.entries(state)) {
      if (fields.has(key) || !derived.has(key)) writable[key] = value;
    }
  });
}

/** A change log collapsed into one summary entry. */
export interface Collapsed {
  summary: string;
  seq: number;
  at: number;
}

/** Replace the change log with a single summary entry; the state is unchanged. */
export function collapse(agent: object, summary: string): Collapsed {
  const own = internalsOf(agent);
  const collapsed: Collapsed = { summary, seq: ++own.seq, at: Date.now() };
  own.changes.length = 0;
  own.changes.push({
    seq: collapsed.seq,
    field: "@summary",
    prev: undefined,
    next: summary,
    author: "collapse",
    at: collapsed.at,
  });
  return collapsed;
}

/** Loads the snapshot a contact's last call left, if any. */
export type LastCall = (contact: string) => Promise<Snapshot | null>;

/** Re-exported for callers reading state and change log together. */

export { changes };
