/** A comparison's rows made the calls a benchmark counts: what a row says of its call, what its log adds, and the round each call is. */

import type { AgentValues, BenchCall, Line, NotCounted } from "./scorecard.js";
import { nameOf } from "./scorecard.js";

/** A comparison's row as a benchmark reads it: the fields of the gateway's row it stands on, whoever typed the rest. */
export interface Row {
  call: string;
  persona: string;
  against: AgentValues;
  started_at: number;
  ended_at: number | null;
  end_reason: string | null;
  score: { passed: boolean; reason: string | null } | null;
  cost_usd: number | null;
  latency: { e2e_latency: number | null; llm_node_ttft: number | null; tts_node_ttfb: number | null; transcription_delay: number | null; end_of_turn_delay?: number | null };
  why: string | null;
  goal?: string | null;
  judges?: { name: string; verdict: string; reason: string }[];
  slowest_reply?: number | null;
  hearing?: Record<string, number | null> | null;
  valid?: boolean;
  invalid?: NotCounted | null;
}

/** One entry of a call's log, as a benchmark reads it. */
export interface Entry {
  ts?: number;
  type: string;
  data: Record<string, unknown>;
}

/** What a call's log and its recording add to its row. Read from the log by `transcript`; a reader with no log gives none of it. */
export interface Read {
  not_counted: NotCounted | null;
  replies_s: number[];
  unpriced: string[];
  recording: string | null;
  timed: boolean;
  lines: Line[];
}

/** Whether the caller got what it came for: its goal's judge, else every judge; null when nobody judged it. */
export function completedOf(row: Row): boolean | null {
  if (row.goal !== undefined && row.goal !== null) return row.goal === "held";
  return row.score === null ? null : row.score.passed;
}

/** One row of a comparison as a benchmark's call, with what was read of its log. */
export function callOf(row: Row & { comparison: string; condition?: string }, read: Read): BenchCall {
  const goal = row.judges?.find((judge) => judge.name === "expected-outcome");
  return {
    call: row.call,
    comparison: row.comparison,
    caller: row.persona,
    setup: nameOf(row.against),
    ...(row.condition === undefined ? {} : { condition: row.condition }),
    round: 0,
    not_counted: read.not_counted,
    completed: completedOf(row),
    reason: goal?.reason ?? row.score?.reason ?? null,
    ended: row.end_reason,
    started_at: row.started_at,
    length_s: row.ended_at === null ? null : row.ended_at - row.started_at,
    reply_s: row.latency.e2e_latency,
    replies_s: read.replies_s,
    slowest_reply_s: row.slowest_reply ?? null,
    cost_usd: row.cost_usd,
    unpriced: read.unpriced,
    stages: { llm_ttft: row.latency.llm_node_ttft, tts_ttfb: row.latency.tts_node_ttfb, transcription_delay: row.latency.transcription_delay, end_of_turn_delay: row.latency.end_of_turn_delay ?? null },
    judges: row.judges ?? [],
    hearing: row.hearing ?? null,
    recording: read.recording,
    timed: read.timed,
    lines: read.lines,
  };
}

// Several comparisons are one table: rounds placed apart. A caller's calls under a setup are numbered
// in the order they started, whichever comparison placed them, and a call that does not count takes
// no round: the one placed in its stead does. Each condition numbers its own.
/** Give each counted call its round: the caller's nth under its setup, in the order they started. */
export function numberRounds(all: BenchCall[]): void {
  const seen = new Map<string, number>();
  for (const call of [...all].sort((one, other) => one.started_at - other.started_at)) {
    if (call.not_counted !== null) continue;
    const pair = `${call.condition ?? ""}\n${call.setup}\n${call.caller}`;
    call.round = (seen.get(pair) ?? 0) + 1;
    seen.set(pair, call.round);
  }
}
