/** Timeline marks for supervisor entries. */

import { eventOf } from "@pinecall/core/wire/codec";
import { type Supervisor } from "@pinecall/core/wire/defs";
import { type Entry } from "@pinecall/core/wire/envelope";

export interface SupervisorMark {
  said: string;
  by: string;
}

// Supervisor entries (docs/protocol/events-control.md); always their own row, never folded.
const A_SUPERVISOR = "supervisor.";

/** The mark for a supervisor entry, or null for any other entry. */
export function supervisorMark(entry: Entry): SupervisorMark | null {
  if (!entry.type.startsWith(A_SUPERVISOR)) {
    return null;
  }
  const event = eventOf(entry);
  switch (event.type) {
    case "supervisor.whispered":
      return { said: `supervisor whispered: ${event.data.text}`, by: named(event.data.by) };
    case "supervisor.said":
      return { said: `supervisor made the agent say: ${event.data.text}`, by: named(event.data.by) };
    case "supervisor.took_over":
      return { said: "supervisor took the line", by: named(event.data.by) };
    case "supervisor.released":
      return { said: "supervisor handed the line back", by: named(event.data.by) };
    case "supervisor.transferred":
      return { said: `supervisor transferred the call to ${event.data.to}`, by: named(event.data.by) };
    case "supervisor.ended":
      return { said: `supervisor ended the call${because(event.data.reason)}`, by: named(event.data.by) };
    default:
      return null;
  }
}

function named(by: Supervisor): string {
  return by.name ?? by.id;
}

function because(reason: string | null | undefined): string {
  return reason === null || reason === undefined ? "" : `: ${reason}`;
}
