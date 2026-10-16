/** Metric names, headline latencies, medians and per-field readings of metrics blocks. */

import { type Entry } from "./wire/envelope.js";
import { type CollectedMetrics, CollectedMetricsSchema, type Turn } from "./wire/state.js";
import { UNITS } from "./wire/units.js";
import { z } from "zod";

import { said, type Shape } from "./compact-json";

/** One formatted measurement, keyed by LiveKit's field name. */
export interface Reading {
  field: string;
  value: string;
  unit: string | null;
}

/** One entry of any `metrics.<block>`. */
export type MetricsBlock = CollectedMetrics[keyof CollectedMetrics][number];

// Headline latencies, split by turn role because each side carries different fields.
const HEADLINE_USER = ["transcription_delay", "end_of_turn_delay"] as const;
const HEADLINE_AGENT = ["llm_node_ttft", "tts_node_ttfb", "e2e_latency"] as const;

/** The five headline latencies, in the order they occur within a turn. */
export const MEASURES = [...HEADLINE_USER, ...HEADLINE_AGENT] as const;

// Must match the runtime's log/reduce.py MEASURES, name and order: the five latencies (end to end the
// caller's wait to the reply's first sound, as the session writes it), then the agent's part of the
// time anybody spoke (`talk_share`, one per call, 0 to 1).
/** Every measure a call is read by, as the runtime folds it. */
export const MEDIANS = [...MEASURES, "talk_share"] as const;

/** The one measure that is a share, not seconds. */
export const TALK_SHARE = "talk_share";

/** Headline readings for a turn; unmeasured fields are omitted, not zero. */
export function headline(turn: Turn): Reading[] {
  return headlineValues(turn).map(([field, value]) => ({
    field,
    value: seconds(value),
    unit: null,
  }));
}

// Units come from the schema's `x-unit` (generated UNITS), never a local table.
/** One reading per filled field of a block; nested objects flattened by dotted name. */
export function readings(block: MetricsBlock, shape?: Shape): Reading[] {
  return rowsOf(block, "", shape);
}

/** JSON Schema of each metrics block, keyed by its CollectedMetrics name. */
export function blockShapes(): Map<string, Shape> {
  const collected = z.toJSONSchema(CollectedMetricsSchema, { io: "input" }) as Shape;
  const shapes = new Map<string, Shape>();
  for (const [kind, field] of Object.entries(collected.properties ?? {})) {
    if (field.items !== undefined) {
      shapes.set(kind, field.items);
    }
  }
  return shapes;
}

/** A measure in its own unit: talk share as a percent, every other one in seconds. */
export function measured(name: string, value: number): string {
  return name === TALK_SHARE ? `${String(Math.round(value * 100))}%` : seconds(value);
}

/** Format a duration in seconds as ms or s. */
export function seconds(value: number): string {
  // LiveKit writes -1 for a time it never measured.
  if (value < 0) {
    return "—";
  }
  return value < 1 ? `${Math.round(value * 1000)} ms` : `${value.toFixed(2)} s`;
}

function rowsOf(source: object, prefix: string, shape?: Shape): Reading[] {
  const found: Reading[] = [];
  for (const [name, value] of Object.entries(source)) {
    const field = prefix + name;
    const declared = shape?.properties?.[name];
    if (value === null || value === undefined) {
      continue;
    }
    if (typeof value === "object" && !Array.isArray(value)) {
      found.push(...rowsOf(value, `${field}.`, declared));
    } else {
      found.push({ field, value: said(value, declared), unit: unitOf(name) });
    }
  }
  return found;
}

function unitOf(field: string): string | null {
  return UNITS[field] ?? null;
}

/** A metrics block's kind and its readings. */
export interface Block {
  kind: string;
  readings: Reading[];
}

// Only llm, tts and eou carry a speech_id; the rest are session-wide.
/** Blocks joined to this turn by speech_id, in log order. */
export function blocksFor(metrics: CollectedMetrics, speechId: string): Block[] {
  const shapes = blockShapes();
  const joined: Block[] = [];
  for (const [kind, blocks] of Object.entries(metrics)) {
    for (const block of blocks) {
      if (joinsTo(block, speechId)) {
        joined.push({ kind, readings: readings(block, shapes.get(kind)) });
      }
    }
  }
  return joined;
}

// The only entries carrying per-turn metrics (as in runtime log/latencies.py).
const TURN_TYPES = ["turn.user", "turn.agent"];

/** One measure over a call: median, max and number of turns that carried it. */
export interface Median {
  name: string;
  seconds: number;
  max: number;
  turns: number;
}

// Median, not mean, so one outlier turn doesn't skew it. Mirrors the runtime's reduce.py so the
// console and `pinecall-runtime sessions show` print the same numbers.
/** One row per measure at least one turn carried, in MEDIANS order. */
export function medians(entries: Entry[]): Median[] {
  const taken = samples(entries);
  return MEDIANS.filter((name) => (taken.get(name) ?? []).length > 0).map((name) => {
    const values = taken.get(name) ?? [];
    return { name, seconds: middle(values), max: Math.max(...values), turns: values.length };
  });
}

function joinsTo(block: MetricsBlock, speechId: string): boolean {
  return "speech_id" in block && block.speech_id === speechId;
}

function headlineValues(turn: Turn): [string, number][] {
  const fields = turn.role === "user" ? HEADLINE_USER : HEADLINE_AGENT;
  const measured = turn.metrics as Record<string, unknown>;
  const found: [string, number][] = [];
  for (const field of fields) {
    const value = measured[field];
    if (typeof value === "number") {
      found.push([field, value]);
    }
  }
  return found;
}

/** When one turn's speaker started and stopped, as livekit stamped it; null where it did not. */
interface Spoken {
  role: "user" | "agent";
  started: number | null;
  stopped: number | null;
}

// The runtime's reduce.py `samples`, word for word: a speaker's time is what each of its turns says
// it spoke.
/** Values of each measure across turns, in order. */
function samples(entries: Entry[]): Map<string, number[]> {
  const found = new Map<string, number[]>(MEDIANS.map((name) => [name, []]));
  const spoke = { user: 0, agent: 0 };
  for (const entry of entries) {
    if (!TURN_TYPES.includes(entry.type)) {
      continue;
    }
    const block = entry.data["metrics"] as Record<string, unknown> | undefined;
    for (const name of MEASURES) {
      const value = block?.[name];
      if (typeof value === "number") {
        found.get(name)?.push(value);
      }
    }
    const turn: Spoken = {
      role: entry.type === "turn.user" ? "user" : "agent",
      started: instant(block?.["started_speaking_at"]),
      stopped: instant(block?.["stopped_speaking_at"]),
    };
    spoke[turn.role] += spokenSeconds(turn);
  }
  if (spoke.agent + spoke.user > 0) {
    found.get(TALK_SHARE)?.push(spoke.agent / (spoke.agent + spoke.user));
  }
  return found;
}

function instant(value: unknown): number | null {
  return typeof value === "number" ? value : null;
}

function spokenSeconds(turn: Spoken): number {
  if (turn.started === null || turn.stopped === null || turn.stopped < turn.started) return 0;
  return turn.stopped - turn.started;
}

// Same as Python's statistics.median (averages the two middle values).
function middle(values: number[]): number {
  const sorted = [...values].sort((first, second) => first - second);
  const half = Math.floor(sorted.length / 2);
  const above = sorted[half] ?? 0;
  return sorted.length % 2 === 1 ? above : ((sorted[half - 1] ?? 0) + above) / 2;
}
