/** The call's log as one column of rows, in the order things happened: turns and tool runs interleaved. */
//
// The state the protocol folds keeps turns and tool runs in two lists, each in
// its own order, joined by the `speech_id` of the reply they belong to: a tool
// with speech id X ran while the agent was working on reply X, so it goes ABOVE
// the agent's turn and below the visitor's. Drawing the two lists one after the
// other instead — every word, then every tool — is a timeline that never
// happened, and the whole point of showing this is that it is the real one.

import { type State } from "./wire/state.js";

export type Row =
  | {
      kind: "turn";
      key: string;
      role: "user" | "agent";
      text: string;
      /** How long the reply took, end to end, when the wire measured it. */
      ms?: number | undefined;
      /** The model's time to its first token: what a written call has instead of `ms`. */
      ttft?: number | undefined;
      interrupted?: boolean | undefined;
    }
  | {
      kind: "tool";
      key: string;
      name: string;
      args: string;
      output?: string | undefined;
      error?: string | undefined;
      status: string;
      /** The arguments and the output as they are, for a page that draws more than one line. */
      raw: { arguments: Record<string, unknown>; output: unknown };
    };

/** A value as one line of JSON, cut where a reader stops caring. */
export function brief(value: unknown, max = 160): string {
  if (value === undefined) return "";
  const written = typeof value === "string" ? value : JSON.stringify(value);
  if (written === undefined) return "";
  return written.length > max ? `${written.slice(0, max - 1)}…` : written;
}

/** Every turn and every tool run, interleaved the way they happened. */
export function rowsOf(state: State): Row[] {
  const rows: Row[] = [];
  const drawn = new Set<string>();

  const tool = (run: State["tools"][number]): Row => ({
    kind: "tool",
    key: `tool-${run.call_id}`,
    name: run.name,
    args: brief(run.arguments),
    output: run.status === "done" ? brief(run.output) : undefined,
    error: run.error ?? undefined,
    status: run.status,
    raw: { arguments: run.arguments, output: run.output },
  });

  for (const [at, turn] of state.turns.entries()) {
    if (turn.role === "agent") {
      for (const run of state.tools) {
        if (run.speech_id !== turn.speech_id || drawn.has(run.call_id)) continue;
        drawn.add(run.call_id);
        rows.push(tool(run));
      }
    }
    rows.push({
      kind: "turn",
      key: `turn-${at}`,
      role: turn.role,
      text: turn.text,
      ms: turn.role === "agent" ? msOf(turn.metrics?.e2e_latency) : undefined,
      ttft: turn.role === "agent" ? msOf(turn.metrics?.llm_node_ttft) : undefined,
      interrupted: turn.role === "agent" ? turn.interrupted : undefined,
    });
  }

  // A tool that is still running belongs after everything said so far: the reply
  // it was called for has not landed yet, which is exactly what it looks like.
  for (const run of state.tools) {
    if (drawn.has(run.call_id)) continue;
    rows.push(tool(run));
  }
  return rows;
}

/** Seconds on the wire, milliseconds on the screen. */
function msOf(seconds: number | null | undefined): number | undefined {
  return typeof seconds === "number" ? Math.round(seconds * 1000) : undefined;
}

/**
 * The agent's own declared fields, in the order the class writes them, minus the empty ones. A
 * field that is an object is opened one level — `person.name`, `person.email` — because a page
 * shows a name, not a JSON blob; anything deeper is written briefly as it is.
 */
export function knownBy(state: State): [string, string][] {
  const rows: [string, string][] = [];
  for (const [name, value] of Object.entries(state.app_state)) {
    if (isRecord(value)) {
      for (const [field, inner] of Object.entries(value)) {
        if (!empty(inner)) rows.push([`${name}.${field}`, brief(inner, 60)]);
      }
    } else if (!empty(value)) rows.push([name, brief(value, 60)]);
  }
  return rows;
}

function empty(value: unknown): boolean {
  return value === null || value === undefined || value === "";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
