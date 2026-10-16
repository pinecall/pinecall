/** Port of the CLI's transcript format: mark, time, payload, and field lines. */

import { type Entry } from "@pinecall/core/wire/envelope";
import { type DocsSources, type MemoryOps } from "@pinecall/core/wire/events";

import { factLines, memoryLine, sourceLines, sourcesLine } from "../../../lib/lookups";
import { compact, said, shapesFor, type Shape } from "@pinecall/core/compact-json";

// Must match the runtime's cli/sessions/render.py (columns, field lines) and log/latencies.py
// (which entries are turns).
const TURN_TYPES = ["turn.user", "turn.agent"];
const METRICS_PREFIX = "metrics.";
// Lookup entries: the summary on the line, results as field lines.
const MEMORY = "memory.ops";
const SOURCES = "docs.sources";

// Mark column: → tool call, ← tool result, ! confirmation.
const MARKS: Record<string, string> = { "tool.call": "→", "tool.result": "←" };
const CONFIRM_MARK = "!";

/** A metrics field: LiveKit's dotted name and the value formatted as the CLI does. */
export interface Field {
  name: string;
  value: string;
}

/** A rendered entry: head line and its field lines. */
export interface Line {
  entry: Entry;
  mark: string;
  since: string;
  payload: string;
  fields: Field[];
}

/** Render every entry, timed from the first, as `pinecall show` does. */
export function transcript(entries: Entry[]): Line[] {
  const shapes = shapesFor(entries.map((entry) => entry.type));
  const origin = entries[0]?.ts ?? 0;
  return entries.map((entry) => lineOf(entry, origin, shapes.get(entry.type)));
}

/** Offset from the call start as `+S.mmm`. */
export function secondsSince(ts: number, origin: number): string {
  return `+${(ts - origin).toFixed(3)}`;
}

function lineOf(entry: Entry, origin: number, shape: Shape | undefined): Line {
  return {
    entry,
    mark: markOf(entry.type),
    since: secondsSince(entry.ts, origin),
    payload: inlinePayload(entry, shape),
    fields: fieldsOf(entry, shape),
  };
}

function markOf(type: string): string {
  if (type.startsWith("confirm.")) {
    return CONFIRM_MARK;
  }
  return MARKS[type] ?? "";
}

// Head line payload: whatever the field lines don't already print in full.
function inlinePayload(entry: Entry, shape: Shape | undefined): string {
  if (TURN_TYPES.includes(entry.type)) {
    const rest = Object.fromEntries(
      Object.entries(entry.data).filter(([name]) => name !== "metrics"),
    );
    return compact(rest, shape);
  }
  if (entry.type.startsWith(METRICS_PREFIX)) {
    return "";
  }
  if (entry.type === MEMORY) {
    return memoryLine(entry.data as MemoryOps);
  }
  if (entry.type === SOURCES) {
    return sourcesLine(entry.data as DocsSources);
  }
  return compact(entry.data, shape);
}

function fieldsOf(entry: Entry, shape: Shape | undefined): Field[] {
  if (TURN_TYPES.includes(entry.type)) {
    const block = entry.data["metrics"];
    const within = shape?.properties?.["metrics"];
    return isBlock(block) ? flattened(block, METRICS_PREFIX, within) : [];
  }
  if (entry.type.startsWith(METRICS_PREFIX)) {
    return flattened(entry.data, "", shape);
  }
  if (entry.type === MEMORY) {
    return factLines(entry.data as MemoryOps).map((value) => ({ name: "fact", value }));
  }
  if (entry.type === SOURCES) {
    return sourceLines(entry.data as DocsSources).map((value) => ({ name: "source", value }));
  }
  return [];
}

// Nested objects flatten to `outer.inner`; lists stay one value. Declared keys come first in
// schema order, since a jsonb round trip reorders keys.
function flattened(block: Record<string, unknown>, prefix: string, shape?: Shape): Field[] {
  return rows(block, prefix, shape, inOrder(block, shape));
}

// Nested objects keep their own key order, as render.py does for `metadata`.
function rows(
  block: Record<string, unknown>,
  prefix: string,
  shape: Shape | undefined,
  names: string[],
): Field[] {
  const found: Field[] = [];
  for (const name of names) {
    const value = block[name];
    const within = shape?.properties?.[name];
    if (isBlock(value)) {
      found.push(...rows(value, `${prefix}${name}.`, within, Object.keys(value)));
    } else {
      found.push({ name: `${prefix}${name}`, value: said(value, within) });
    }
  }
  return found;
}

function inOrder(block: Record<string, unknown>, shape?: Shape): string[] {
  const declared = Object.keys(shape?.properties ?? {}).filter((name) => name in block);
  return [...declared, ...Object.keys(block).filter((name) => !declared.includes(name))];
}

function isBlock(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
