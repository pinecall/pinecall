/** Timeline marks for line events: transfer, hold, attention, callback. */

import { eventOf } from "@pinecall/core/wire/codec";
import { type Entry } from "@pinecall/core/wire/envelope";

export interface LineMark {
  said: string;
  note: string | null;
}

// Line entries (runtime docs/protocol/the-line.md); always shown as their own row, never folded.
const THE_LINE = new Set(["call.transferred", "call.line", "attention.requested", "attention.answered", "callback.requested"]);

/** The mark for a line entry, or null for any other entry. */
export function lineMark(entry: Entry): LineMark | null {
  if (!THE_LINE.has(entry.type)) {
    return null;
  }
  const event = eventOf(entry);
  switch (event.type) {
    case "call.transferred":
      return event.data.ok
        ? { said: `transferred to ${event.data.to}`, note: event.data.mode ?? null }
        : { said: `the transfer to ${event.data.to} did not take`, note: event.data.error ?? null };
    case "call.line":
      return { said: event.data.held ? "the caller is on hold" : "the caller is off hold", note: null };
    case "attention.requested":
      return { said: `the agent asked for a person: ${event.data.reason}`, note: `waits ${String(event.data.wait_s)}s` };
    case "attention.answered":
      return event.data.ok
        ? { said: "a person took the line", note: event.data.by === null ? null : (event.data.by.name ?? event.data.by.id) }
        : { said: "nobody took the line", note: event.data.error ?? null };
    case "callback.requested":
      return { said: `asked to be called back on ${event.data.number}`, note: event.data.when ?? null };
    default:
      return null;
  }
}
