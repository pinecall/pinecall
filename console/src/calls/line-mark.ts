/** The marks line events leave on a conversation: a transfer, a hold, a call for a person, a call back. */

import { eventOf } from "@pinecall/core/wire/codec";
import { type Entry } from "@pinecall/core/wire/envelope";

export interface LineMark {
  said: string;
  note: string | null;
}

// Line entries are always a row of their own, never folded.
const THE_LINE = new Set(["call.transferred", "call.line", "attention.requested", "attention.answered", "callback.requested"]);

/** The mark for a line entry, or null for any other entry. */
export function lineMark(entry: Entry): LineMark | null {
  if (!THE_LINE.has(entry.type)) return null;
  const event = eventOf(entry);
  switch (event.type) {
    case "call.transferred":
      return event.data.ok ? { said: `Transferred to ${event.data.to}`, note: event.data.mode ?? null } : { said: `The transfer to ${event.data.to} did not take`, note: event.data.error ?? null };
    case "call.line":
      return { said: event.data.held ? "The caller is on hold" : "The caller is off hold", note: null };
    case "attention.requested":
      return { said: `The agent asked for a person: ${event.data.reason}`, note: `waits ${String(event.data.wait_s)}s` };
    case "attention.answered":
      return event.data.ok ? { said: "A person took the line", note: event.data.by === null ? null : (event.data.by.name ?? event.data.by.id) } : { said: "Nobody took the line", note: event.data.error ?? null };
    case "callback.requested":
      return { said: `Asked to be called back on ${event.data.number}`, note: event.data.when ?? null };
    default:
      return null;
  }
}
