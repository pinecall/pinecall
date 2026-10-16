/** Where a finished call's time went: every instant of it given to exactly one kind, so the parts add up to its length. */

import { eventOf } from "@pinecall/core/wire/codec";
import { type Entry } from "@pinecall/core/wire/envelope";
import { type State } from "@pinecall/core/wire/state";

import { traceOf, type Trace, type TraceBar } from "../trace-bars";

/**
 * What an instant of the call was: a person holding the line instead of the agent, somebody
 * speaking (one side, or both over each other), or a silence, named by who it was waiting on — a
 * tool running, or else whoever did not speak last.
 */
export type Spent = "before" | "caller" | "agent" | "both" | "on_the_agent" | "tool" | "on_the_caller" | "person";

/** The order the parts are drawn and listed in. */
const SPENT: readonly Spent[] = ["before", "caller", "agent", "both", "on_the_agent", "tool", "on_the_caller", "person"];

/** A stretch of the call, in seconds from its start. */
interface Span {
  from: number;
  to: number;
}

export interface TimeSpent {
  /** Seconds from the call's start to its end. */
  length: number;
  /** One per kind the call had any of, in SPENT order; their seconds add up to `length`. */
  parts: { kind: Spent; seconds: number }[];
}

/** A call that is over, read for where its time went; null while it is live or when nobody was heard. */
export function timeSpentIn(entries: Entry[], state: State): TimeSpent | null {
  if (state.started_at === null || state.ended_at === null) return null;
  const length = state.ended_at - state.started_at;
  return timeSpent(traceOf(entries, state), length, withAPerson(entries, state.started_at, length));
}

const HANDS = new Set(["supervisor.took_over", "supervisor.released", "call.transferred"]);

// A transfer that took hands the caller to a person until the end (every transfer, the agent's or
// a supervisor's, writes one `call.transferred`), and a supervisor who took the line holds it until
// they release it. Either way the agent is out of the conversation, whoever is heard.
function withAPerson(entries: Entry[], start: number, length: number): Span[] {
  const spans: Span[] = [];
  let took: number | null = null;
  // Only these three are read: an older entry of another type need not parse as today's wire.
  for (const entry of entries.filter((one) => HANDS.has(one.type))) {
    const at = entry.ts - start;
    const event = eventOf(entry);
    if (event.type === "supervisor.took_over" && took === null) took = at;
    if (event.type === "supervisor.released" && took !== null) {
      spans.push({ from: took, to: at });
      took = null;
    }
    if (event.type === "call.transferred" && event.data.ok) {
      spans.push({ from: took ?? at, to: length });
      return spans;
    }
  }
  if (took !== null) spans.push({ from: took, to: length });
  return spans;
}

// The intervals are the Trace's own bars — the speaking times livekit stamped on each turn, a tool
// from its `tool.call` to its reported duration — and the stretches a person held the line, cut at
// every edge; each piece between two edges is one kind. A person holding the line wins over
// everything, and speaking over a tool: a tool that runs while the agent talks costs nobody.
/** `length` is the call's, and every instant in the trace's seconds from its start. */
function timeSpent(trace: Trace, length: number, person: Span[]): TimeSpent | null {
  const bars = trace.rows.flatMap((row) => row.bars);
  const speech = bars.filter((bar) => bar.kind === "caller" || bar.kind === "agent").map((bar) => clipped(bar, length)).filter((bar) => bar.to > bar.from);
  if (speech.length === 0 || length <= 0) return null;
  const tools = bars.filter((bar) => bar.kind === "tool").map((bar) => clipped(bar, length)).filter((bar) => bar.to > bar.from);

  const held = person.map((span) => clipped(span, length)).filter((span) => span.to > span.from);

  const edges = [...new Set([0, length, ...[...speech, ...tools, ...held].flatMap((span) => [span.from, span.to])])].sort((a, b) => a - b);
  const total = new Map<Spent, number>();
  edges.slice(1).forEach((to, index) => {
    const from = edges[index] ?? to;
    const middle = (from + to) / 2;
    const kind = held.some((span) => span.from <= middle && middle < span.to) ? "person" : kindAt(middle, from, speech, tools);
    total.set(kind, (total.get(kind) ?? 0) + (to - from));
  });
  return { length, parts: SPENT.filter((kind) => total.has(kind)).map((kind) => ({ kind, seconds: total.get(kind) ?? 0 })) };
}

function kindAt(middle: number, from: number, speech: TraceBar[], tools: TraceBar[]): Spent {
  const on = (bar: TraceBar): boolean => bar.from <= middle && middle < bar.to;
  const caller = speech.some((bar) => bar.kind === "caller" && on(bar));
  const agent = speech.some((bar) => bar.kind === "agent" && on(bar));
  if (caller && agent) return "both";
  if (caller) return "caller";
  if (agent) return "agent";
  if (tools.some(on)) return "tool";
  const last = lastToStop(speech, from);
  if (last === null) return "before";
  return last === "caller" ? "on_the_agent" : "on_the_caller";
}

// Who spoke last before a silence: the one whose speaking stopped latest, no later than it began.
function lastToStop(speech: TraceBar[], at: number): TraceBar["kind"] | null {
  let last: TraceBar | null = null;
  for (const bar of speech) {
    if (bar.to <= at && (last === null || bar.to > last.to)) last = bar;
  }
  return last?.kind ?? null;
}

function clipped<T extends Span>(span: T, length: number): T {
  return { ...span, from: Math.max(0, span.from), to: Math.min(length, span.to) };
}
