/** An entry of the log read as the event its type names, typed. */

import { z } from "zod";
import { type Entry, EntrySchema } from "./envelope.js";
import { EVENT_SCHEMAS, type EventType } from "./registry.js";

export class UnknownType extends Error {
  override readonly name = "UnknownType";
}

/** The data shape of one event type. */
export type EventData<K extends EventType> = z.infer<(typeof EVENT_SCHEMAS)[K]>;

/** One event, typed by its type: switch on `type` and `data` narrows with it. */
export type Event = { [K in EventType]: { type: K; data: EventData<K> } }[EventType];

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

