/** An entry read as the event its type names, typed; and the one place a key is renamed. */

import { z } from "zod";
import { type Entry, EntrySchema } from "./envelope.js";
import { COMMAND_SCHEMAS, type CommandType, EVENT_SCHEMAS, type EventType } from "./registry.js";

export class UnknownType extends Error {
  override readonly name = "UnknownType";
}

/** The data shape of one event type. */
export type EventData<K extends EventType> = z.infer<(typeof EVENT_SCHEMAS)[K]>;

/** One event, typed by its type: switch on `type` and `data` narrows with it. */
export type Event = { [K in EventType]: { type: K; data: EventData<K> } }[EventType];

/** The data shape of one command type. */
export type CommandData<K extends CommandType> = z.infer<(typeof COMMAND_SCHEMAS)[K]>;

/** One log line from decoded JSON. A bad shape throws. */
export function decodeEntry(raw: unknown): Entry {
  return EntrySchema.parse(raw);
}

/** The entry's data as the shape its type names; an unknown type or a bad shape throws. */
export function eventOf(entry: Entry): Event {
  if (!isEventType(entry.type)) {
    throw new UnknownType(`unknown event type: ${entry.type}`);
  }
  return { type: entry.type, data: EVENT_SCHEMAS[entry.type].parse(entry.data) } as Event;
}

export function isEventType(type: string): type is EventType {
  return Object.hasOwn(EVENT_SCHEMAS, type);
}

// ── key names ──────────────────────────────────────────────────────────────────

/** "llm_node_ttft" as a type becomes "llmNodeTtft". */
export type CamelCase<S extends string> = S extends `${infer Head}_${infer Tail}`
  ? `${Head}${Capitalize<CamelCase<Tail>>}`
  : S;

/** "llmNodeTtft" as a type becomes "llm_node_ttft". */
export type SnakeCase<S extends string> = S extends `${infer Head}${infer Tail}`
  ? Head extends Lowercase<Head>
    ? `${Head}${SnakeCase<Tail>}`
    : `_${Lowercase<Head>}${SnakeCase<Tail>}`
  : S;

/** A wire shape with every key camelCased, deep, except under the opaque keys. */
export type Camel<T> = T extends readonly (infer Item)[]
  ? Camel<Item>[]
  : T extends object
    ? { [K in keyof T as K extends string ? CamelCase<K> : K]: K extends OpaqueKey ? T[K] : Camel<T[K]> }
    : T;

/** A camelCased shape back to the wire's keys, deep, except under the opaque keys. */
export type Snake<T> = T extends readonly (infer Item)[]
  ? Snake<Item>[]
  : T extends object
    ? { [K in keyof T as K extends string ? SnakeCase<K> : K]: K extends OpaqueKey ? T[K] : Snake<T[K]> }
    : T;

/** The keys whose values belong to the app (its state, a tool's arguments, a plugin's options, a map it named): never renamed below them. */
export const OPAQUE_KEYS = new Set<string>(["app_state", "arguments", "attributes", "data", "facts", "input", "metadata", "options", "output", "parameters", "prompt", "result", "state"]);
export type OpaqueKey = "app_state" | "arguments" | "attributes" | "data" | "facts" | "input" | "metadata" | "options" | "output" | "parameters" | "prompt" | "result" | "state";

/** Rename every key from snake_case to camelCase, deep. Values are never touched. */
export function toCamel<T>(value: T): Camel<T> {
  return renameKeys(value, camelCase) as Camel<T>;
}

/** Rename every key from camelCase to snake_case, deep. Values are never touched. */
export function toSnake<T>(value: T): Snake<T> {
  return renameKeys(value, snakeCase) as Snake<T>;
}

function renameKeys(value: unknown, rename: (key: string) => string): unknown {
  if (Array.isArray(value)) {
    return value.map((item) => renameKeys(item, rename));
  }
  if (value === null || typeof value !== "object") {
    return value;
  }
  const renamed: Record<string, unknown> = {};
  for (const [key, inner] of Object.entries(value)) {
    renamed[rename(key)] = OPAQUE_KEYS.has(key) ? inner : renameKeys(inner, rename);
  }
  return renamed;
}

function camelCase(key: string): string {
  return key.replace(/_([a-z0-9])/g, (_, letter: string) => letter.toUpperCase());
}

function snakeCase(key: string): string {
  return key.replace(/[A-Z]/g, (letter) => `_${letter.toLowerCase()}`);
}
