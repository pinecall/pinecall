/** Build the call timeline rows (turns, tools, state, confirmations, facts) from log entries. */

import { eventOf } from "@pinecall/core/wire/codec";
import { type EventSource } from "@pinecall/core/wire/defs";
import { type Entry } from "@pinecall/core/wire/envelope";
import { type DocsSources, type MemoryOps, type StateCause } from "@pinecall/core/wire/events";
import { type Confirm, type State, type ToolRun, type Turn } from "@pinecall/core/wire/state";

import { lineMark, type LineMark } from "../../lib/line-mark";
import { supervisorMark, type SupervisorMark } from "../../lib/supervisor-mark";

/** A timeline row, tagged with the seq of its entry. */
export type Row =
  | { kind: "turn"; seq: number; turn: Turn }
  | { kind: "tool"; seq: number; run: ToolRun }
  | { kind: "state"; seq: number; changed: string[]; cause: StateCause | null }
  | { kind: "confirm"; seq: number; confirm: Confirm }
  | { kind: "event"; seq: number; name: string; source: EventSource; data: Record<string, unknown> }
  | { kind: "supervisor"; seq: number; mark: SupervisorMark }
  | { kind: "line"; seq: number; mark: LineMark }
  | { kind: "memory"; seq: number; ops: MemoryOps }
  | { kind: "sources"; seq: number; sources: DocsSources }
  | { kind: "quiet"; seq: number; entries: Entry[] };

/**
 * Non-turn rows show the reducer's object (ToolRun, Confirm) looked up by the entry's id: the entry
 * gives the position, the state gives the outcome.
 */
export function rowsOf(entries: Entry[], state: State): Row[] {
  const rows: Row[] = [];
  let quiet: Entry[] = [];
  // `turn.agent` is logged when speech ends, but tools run while it plays, so in log order the tool
  // precedes the sentence announcing it. Place agent turns at their `agent.state → speaking` instead.
  const spokenAt = beganSpeaking(entries);

  const flush = (): void => {
    if (quiet.length > 0) {
      rows.push({ kind: "quiet", seq: quiet[0]?.seq ?? 0, entries: quiet });
      quiet = [];
    }
  };

  for (const entry of entries) {
    const row = rowOf(entry, state);
    if (row === null) {
      quiet.push(entry);
      continue;
    }
    flush();
    rows.push(row);
  }
  flush();
  return inTheOrderItWasHeard(rows, spokenAt);
}

/** Map each agent turn's seq to the seq of the `speaking` state that started it. */
function beganSpeaking(entries: Entry[]): Map<number, number> {
  const at = new Map<number, number>();
  let began: number | null = null;
  for (const entry of entries) {
    if (entry.type === "agent.state") {
      const state = (entry.data as { state?: string }).state;
      if (state === "speaking" && began === null) began = entry.seq;
      if (state === "listening") began = null;
    }
    if (entry.type === "turn.agent" && began !== null) {
      at.set(entry.seq, began);
      // Only the first turn of a multi-sentence reply takes the `speaking` seq, to keep their order.
      began = null;
    }
  }
  return at;
}

/** Reorder rows by when they were heard rather than when they were logged. */
function inTheOrderItWasHeard(rows: Row[], spokenAt: Map<number, number>): Row[] {
  const when = (row: Row): number => (row.kind === "turn" ? (spokenAt.get(row.seq) ?? row.seq) : row.seq);
  // Stable: ties keep log order.
  return rows
    .map((row, at) => ({ row, at, when: when(row) }))
    .sort((a, b) => a.when - b.when || a.at - b.at)
    .map((one) => one.row);
}

// null: not a conversation row (metrics, session state, prompt); folded into a quiet row.
function rowOf(entry: Entry, state: State): Row | null {
  const seq = entry.seq;
  // Supervisor entries are never folded; shared with the Talk screen (lib/supervisor-mark.ts).
  const supervised = supervisorMark(entry);
  if (supervised !== null) {
    return { kind: "supervisor", seq, mark: supervised };
  }
  // Same for line events: transfer, hold, human requested (lib/line-mark.ts).
  const moved = lineMark(entry);
  if (moved !== null) {
    return { kind: "line", seq, mark: moved };
  }
  // An entry this reader no longer knows the shape of is the reducer's error (UNREADABLE), not a
  // row: an older log draws what it can, and never takes the screen down with it.
  let event: ReturnType<typeof eventOf>;
  try {
    event = eventOf(entry);
  } catch {
    return null;
  }
  switch (event.type) {
    case "turn.user":
    case "turn.agent": {
      const turn = turnOf(state, event.type === "turn.user" ? "user" : "agent", event.data);
      return turn === undefined ? null : { kind: "turn", seq, turn };
    }
    case "tool.call": {
      const run = last(state.tools, (one) => one.call_id === event.data.call_id);
      return run === undefined ? null : { kind: "tool", seq, run };
    }
    case "state.changed":
      return { kind: "state", seq, changed: event.data.changed, cause: event.data.cause ?? null };
    case "confirm.request": {
      const confirm = last(state.confirms, (one) => one.call_id === event.data.call_id);
      return confirm === undefined ? null : { kind: "confirm", seq, confirm };
    }
    case "event.received":
      return {
        kind: "event",
        seq,
        name: event.data.name,
        source: event.data.source,
        data: event.data.data,
      };
    case "memory.ops":
      return { kind: "memory", seq, ops: event.data };
    case "docs.sources":
      return { kind: "sources", seq, sources: event.data };
    // Transcript deltas render as the live row; finals arrive as turns.
    default:
      return null;
  }
}

// Match by `item_id` first: one `speech_id` can hold several `turn.agent` utterances, and matching
// by reply would show the last one on every row.
function turnOf(state: State, role: Turn["role"], said: { speech_id: string; item_id?: string | null | undefined }): Turn | undefined {
  const item = said.item_id;
  if (typeof item === "string" && item !== "") {
    const one = last(state.turns, (turn) => turn.role === role && turn.item_id === item);
    if (one !== undefined) return one;
  }
  return last(state.turns, (turn) => turn.role === role && turn.speech_id === said.speech_id);
}

function last<T>(items: T[], matches: (item: T) => boolean): T | undefined {
  for (let index = items.length - 1; index >= 0; index -= 1) {
    const item = items[index] as T;
    if (matches(item)) {
      return item;
    }
  }
  return undefined;
}
