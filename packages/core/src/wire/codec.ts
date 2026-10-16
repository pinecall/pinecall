/** The log's entry read as the event its type names, typed: switch on `type` and `data` narrows. */

import { z } from "zod";
import { type Entry, EntrySchema } from "./envelope.js";
import { EVENT_SCHEMAS, type EventType } from "./registry.js";

/** An entry whose type no event of the wire names. */
export class UnknownEvent extends Error {
  override readonly name = "UnknownEvent";
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
    throw new UnknownEvent(`unknown event type: ${entry.type}`);
  }
  return { type: entry.type, data: EVENT_SCHEMAS[entry.type].parse(entry.data) } as Event;
}

/** Whether an entry's type is an event of the wire. */
export function isEventType(type: string): type is EventType {
  return Object.hasOwn(EVENT_SCHEMAS, type);
}
