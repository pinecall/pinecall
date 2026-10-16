/** The live terminal view as pure functions: events in, screen text out. */

import type { CamelEvent } from "@pinecall/agents/client";
import { toSnake } from "@pinecall/agents/wire";

import { lineFor, metricsLine, type Line } from "../calls/render.js";

export { BROKE, CALLER, lineFor, metricsLine, TURN_METRICS, type Line } from "../calls/render.js";

/** View state folded from events. */
export interface Screen {
  slug: string;
  url: string;
  calls: number;
  transcript: Line[];
  tools: Line[];
  state: Record<string, unknown>;
  /** Fields named by the last state.changed, highlighted in the STATE panel. */
  changed: string[];
  metrics: string[];
  events: string[];
}

// Max lines kept per panel.
const KEPT = 200;

/** An empty view. */
export function screenFor(slug: string, url: string): Screen {
  return { slug, url, calls: 0, transcript: [], tools: [], state: {}, changed: [], metrics: [], events: [] };
}

/** Fold one event into the view and return the next screen. Pure. */
export function absorb(screen: Screen, event: CamelEvent): Screen {
  const next: Screen = { ...screen, events: keep([...screen.events, JSON.stringify(event)]) };
  switch (event.type) {
    case "call.started":
      return { ...next, calls: screen.calls + 1 };
    case "turn.user":
      return { ...next, transcript: keep([...screen.transcript, lineFor(event)!]) };
    case "turn.agent":
      return {
        ...next,
        transcript: keep([...screen.transcript, lineFor(event)!]),
        metrics: keep([...screen.metrics, metricsLine(toSnake(event.data.metrics))]),
      };
    case "tool.call":
    case "tool.result":
      return { ...next, tools: keep([...screen.tools, lineFor(event)!]) };
    case "state.changed":
      return { ...next, state: { ...event.data.state }, changed: [...event.data.changed] };
    default:
      return next;
  }
}

/** The STATE panel: one field per line, recently changed ones marked with a dot. */
export function statePanel(state: Record<string, unknown>, changed: string[]): string[] {
  const names = Object.keys(state);
  if (names.length === 0) return ["  (no state yet)"];
  return names.map((name) => `${changed.includes(name) ? "● " : "  "}${name}: ${short(state[name])}`);
}

/** Render the view as text clipped to the terminal size. */
export function draw(screen: Screen, rows: number, columns: number, raw = false): string {
  const body = raw ? screen.events.slice(-(rows - 4)) : panels(screen, rows);
  const lines = [`pinecall ${screen.slug}  ${screen.url}  calls ${screen.calls}`, divider(columns), ...body];
  return lines.map((line) => line.slice(0, columns)).join("\n");
}

// Transcript, TOOLS, STATE, metrics; the transcript takes the remaining height.
function panels(screen: Screen, rows: number): string[] {
  const state = statePanel(screen.state, screen.changed);
  const tools = screen.tools.slice(-5);
  const metric = screen.metrics.at(-1);
  const height = Math.max(3, rows - state.length - tools.length - 9);
  return [
    ...screen.transcript.slice(-height).map((line) => `${line.mark} ${line.text}`),
    "",
    "TOOLS",
    ...tools.map((line) => `${line.mark} ${line.text}`),
    "",
    "STATE",
    ...state,
    "",
    `metrics  ${metric ?? "—"}`,
  ];
}

function divider(columns: number): string {
  return "─".repeat(Math.max(1, Math.min(columns, 100)));
}

// JSON, truncated to `width`.
function short(value: unknown, width = 60): string {
  const text = typeof value === "string" ? value : (JSON.stringify(value) ?? String(value));
  return text.length > width ? `${text.slice(0, width - 1)}…` : text;
}

function keep<T>(lines: T[]): T[] {
  return lines.length > KEPT ? lines.slice(-KEPT) : lines;
}
