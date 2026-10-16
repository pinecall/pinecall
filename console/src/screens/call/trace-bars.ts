/** Fold a call's turns, metrics blocks and tools into rows of bars on one time axis, for the Trace view. */

import { type Entry } from "@pinecall/core/wire/envelope";
import { type CollectedMetrics, type State, type ToolRun, type Turn } from "@pinecall/core/wire/state";

/** What a bar is a bar of: someone speaking, or one stage of the work between. */
export type BarKind = "caller" | "eou" | "llm" | "voice" | "tool" | "agent";

/** What the pane shows when a bar is clicked: the block, tool or turn behind it, as the state holds it. */
export type Behind =
  | { kind: "block"; block: "eou" | "llm" | "tts"; at: CollectedMetrics["eou" | "llm" | "tts"][number] }
  | { kind: "tool"; run: ToolRun }
  | { kind: "turn"; turn: Turn };

/** One bar. Instants are seconds from the call's start. */
export interface TraceBar {
  /** Stable across a live call's updates: the state's arrays only grow. */
  id: string;
  kind: BarKind;
  label: string;
  from: number;
  to: number;
  /** The first token, the first byte, the final transcript: an instant inside the bar, when one was measured. */
  tick: number | null;
  /** Cancelled, interrupted or failed. */
  cut: boolean;
  behind: Behind;
}

/** One exchange: everything that shares a speech_id, the caller's turn and the reply to it. */
export interface TraceRow {
  speech: string;
  /** What the caller said, or the agent when it spoke unprompted; null when neither has a turn yet. */
  said: string | null;
  bars: TraceBar[];
}

export interface Trace {
  /** Seconds from the call's start to the last thing measured or logged. */
  span: number;
  rows: TraceRow[];
}

// The order bars of one exchange are drawn in when they start together.
const ORDER: readonly BarKind[] = ["caller", "eou", "llm", "tool", "voice", "agent"];

/**
 * Every bar is placed by an instant that was measured, never by adding up other stages. A block
 * with no instant, or a turn with no speaking times (a typed one), draws nothing.
 */
export function traceOf(entries: Entry[], state: State): Trace {
  const start = state.started_at ?? entries[0]?.ts ?? 0;
  const at = (instant: number): number => instant - start;
  const bars: { speech: string; bar: TraceBar }[] = [];
  const add = (speech: string | null | undefined, bar: TraceBar | null): void => {
    if (bar !== null) bars.push({ speech: speech ?? "", bar });
  };

  state.turns.forEach((turn, index) => add(turn.speech_id, spoken(turn, index, at)));
  state.metrics.eou.forEach((block, index) => {
    const span = endingAt(block.timestamp, block.end_of_utterance_delay + block.on_user_turn_completed_delay);
    add(block.speech_id, {
      id: `eou-${String(index)}`,
      kind: "eou",
      label: "end of turn",
      from: at(span.from),
      to: at(span.to),
      tick: at(span.from + block.transcription_delay),
      cut: false,
      behind: { kind: "block", block: "eou", at: block },
    });
  });
  state.metrics.llm.forEach((block, index) => {
    const span = endingAt(block.timestamp, block.duration);
    add(block.speech_id, {
      id: `llm-${String(index)}`,
      kind: "llm",
      label: block.metadata?.model_name ?? "llm",
      from: at(span.from),
      to: at(span.to),
      tick: block.ttft < 0 ? null : at(span.from + block.ttft),
      cut: block.cancelled,
      behind: { kind: "block", block: "llm", at: block },
    });
  });
  state.metrics.tts.forEach((block, index) => {
    const span = endingAt(block.timestamp, block.duration);
    add(block.speech_id, {
      id: `voice-${String(index)}`,
      kind: "voice",
      label: "voice",
      from: at(span.from),
      to: at(span.to),
      tick: block.ttfb < 0 ? null : at(span.from + block.ttfb),
      cut: block.cancelled,
      behind: { kind: "block", block: "tts", at: block },
    });
  });
  const logged = new Map(entries.map((entry) => [entry.seq, entry.ts]));
  for (const run of state.tools) add(run.speech_id, ran(run, logged.get(run.seq), at));

  const last = Math.max(0, ...bars.map(({ bar }) => bar.to), at(entries.at(-1)?.ts ?? start));
  return { span: last, rows: rowsOf(bars, state.turns) };
}

// LiveKit stamps a block when its work ENDS: `timestamp=time.time()` once the stream has drained
// (livekit-agents 1.8, llm.py and tts.py; the eou after on_user_turn_completed). Read on the box,
// an LLM's timestamp minus its duration lands on the end of turn it answered, and a voice's start
// plus its ttfb on the moment the agent began speaking. Its own length reaches back from there.
function endingAt(timestamp: number, length: number): { from: number; to: number } {
  return { from: timestamp - length, to: timestamp };
}

function spoken(turn: Turn, index: number, at: (instant: number) => number): TraceBar | null {
  const began = turn.metrics.started_speaking_at;
  const ended = turn.metrics.stopped_speaking_at;
  if (typeof began !== "number" || typeof ended !== "number") return null;
  return {
    id: `turn-${String(index)}`,
    kind: turn.role === "user" ? "caller" : "agent",
    label: turn.role === "user" ? "caller" : "agent",
    from: at(began),
    to: at(ended),
    tick: null,
    cut: turn.role === "agent" && turn.interrupted,
    behind: { kind: "turn", turn },
  };
}

// A tool starts when its `tool.call` was logged; it has a length once its result came back.
function ran(run: ToolRun, called: number | undefined, at: (instant: number) => number): TraceBar | null {
  if (called === undefined) return null;
  return {
    id: `tool-${run.call_id}`,
    kind: "tool",
    label: run.name,
    from: at(called),
    to: at(called + (run.duration_s ?? 0)),
    tick: null,
    cut: run.status === "failed",
    behind: { kind: "tool", run },
  };
}

// One row per speech_id, in the order the exchanges began; inside one, bars by when they began.
function rowsOf(bars: { speech: string; bar: TraceBar }[], turns: Turn[]): TraceRow[] {
  const rows = new Map<string, TraceBar[]>();
  for (const { speech, bar } of bars) rows.set(speech, [...(rows.get(speech) ?? []), bar]);
  return [...rows.entries()]
    .map(([speech, held]) => ({
      speech,
      said: saidIn(turns, speech),
      bars: [...held].sort((a, b) => a.from - b.from || ORDER.indexOf(a.kind) - ORDER.indexOf(b.kind)),
    }))
    .sort((a, b) => (a.bars[0]?.from ?? 0) - (b.bars[0]?.from ?? 0));
}

function saidIn(turns: Turn[], speech: string): string | null {
  const ours = turns.filter((turn) => turn.speech_id === speech);
  return (ours.find((turn) => turn.role === "user") ?? ours[0])?.text ?? null;
}
