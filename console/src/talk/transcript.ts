/** What the talk panel draws: the two voices as the room says them — the caller's settled into the log's turns — each tool the model ran as one card, and the log's marks between them. */

import { type Entry } from "@pinecall/core/wire/envelope";
import type { Said } from "@pinecall/core/transcripts";

import { stageSaid } from "./stages";
import { supervisorMark } from "./supervisor-mark";

export type { Said, Speaker } from "@pinecall/core/transcripts";
export { SEGMENT_ID, TRANSCRIPTION_FINAL, TRANSCRIPTION_TOPIC, upsert } from "@pinecall/core/transcripts";

/** One thing the log said between two sentences: an error, a supervisor stepping in, or a stage of the call changed. */
export interface Mark {
  kind: "mark";
  id: string;
  tone: "error" | "supervisor" | "change";
  text: string;
}

/** One tool the model ran: its call and, once the app answered, its result — one card, keyed by the call's id. */
export interface ToolRun {
  kind: "tool";
  id: string;
  name: string;
  /** Null on a result that arrived before its call was seen: the call fills it in. */
  args: Record<string, unknown> | null;
  status: "running" | "ok" | "failed";
  /** The summary the app wrote, else the output or the error, as text. */
  result: string | null;
  /** What the app answered, as it answered it: read into a view (tool-shape.ts); undefined until it does. */
  output: unknown;
  seconds: number | null;
}

export type Line = Said | Mark | ToolRun;

// What a person TYPES reaches the same session on this topic: livekit-agents' text input, read
// from the participant the session is pinned to — the caller, which is this tab. The agent answers
// it out loud, in the same call, as it answers a spoken turn.
export const CHAT_TOPIC = "lk.chat";

// A tool the model calls is logged the instant it asks for it; the sentence that announces it
// reaches the page only as the voice says it, a beat later. A mark that arrives before the agent
// has spoken waits this long for the agent's next sentence, and is placed under it.
export const A_BEAT_MS = 1500;

const BROKE = "✗";

/** The words of a line, keeping the spaces, so the renderer can animate each arrival once. */
export function words(text: string): string[] {
  return text.split(/(\s+)/).filter((part) => part.length > 0);
}

/** A tool's card with what a later entry says about it: the call's name and arguments, the result's outcome. */
export function joined(was: ToolRun, now: ToolRun): ToolRun {
  return now.args === null ? { ...now, args: was.args, name: was.name } : { ...was, args: now.args };
}

/**
 * The lines once the log has closed a caller's turn: the stretches the ear heard to the end since
 * the last turn give way to ONE bubble with the turn's own words, where the first of them stood —
 * keeping that one's id, so the bubble is not drawn anew. A stretch still being heard belongs to the
 * next turn and stays. A written line is never one of them: it waits for its own turn by its words.
 */
export function landed(lines: Line[], text: string): { lines: Line[]; replaced: string[] } {
  const heard = lines.filter((line): line is Said => line.kind === "said" && line.speaker === "user" && line.final && line.pending === undefined && line.landed !== true);
  const first = heard[0];
  if (first === undefined) return { lines, replaced: [] };
  const whole = text.trim() !== "" ? text.trim() : heard.map((line) => line.text.trim()).join(" ");
  const gone = new Set(heard.map((line) => line.id));
  const turn: Said = { ...first, text: whole, landed: true };
  return { lines: lines.flatMap((line) => (line.id === first.id ? [turn] : gone.has(line.id) ? [] : [line])), replaced: [...gone] };
}

/** The line one entry of the log is worth on this screen, or null when it is worth none. */
export function markOf(entry: Entry): Mark | ToolRun | null {
  // A supervisor can whisper into this call too, and it reads here the way it reads on the Calls
  // screen: one sentence, written once, in lib/supervisor-mark.ts.
  const supervised = supervisorMark(entry);
  if (supervised !== null) {
    return { kind: "mark", id: `mark-${entry.seq}`, tone: "supervisor", text: supervised.said };
  }
  const data = entry.data as Record<string, unknown>;
  switch (entry.type) {
    case "tool.call":
      return {
        kind: "tool",
        id: `tool-${String(data["call_id"])}`,
        name: String(data["name"]),
        args: (data["arguments"] as Record<string, unknown> | undefined) ?? {},
        status: "running",
        result: null,
        output: undefined,
        seconds: null,
      };
    case "tool.result": {
      const failed = data["error"] !== undefined && data["error"] !== null;
      return {
        kind: "tool",
        id: `tool-${String(data["call_id"])}`,
        name: String(data["name"]),
        args: null,
        status: failed ? "failed" : "ok",
        result: answered(data),
        output: failed ? undefined : data["output"],
        seconds: typeof data["duration_s"] === "number" ? data["duration_s"] : null,
      };
    }
    case "error":
      return { kind: "mark", id: `mark-${entry.seq}`, tone: "error", text: `${BROKE} ${String(data["message"])}` };
    case "stage.changed": {
      const said = stageSaid(data);
      return said === null ? null : { kind: "mark", id: `mark-${entry.seq}`, tone: "change", text: said };
    }
    default:
      return null;
  }
}

// The whole answer, pretty-printed: the card shows it folded, and a person unfolds it to read it.
function answered(data: Record<string, unknown>): string {
  if (data["error"] !== undefined && data["error"] !== null) return said(data["error"]);
  if (data["output"] !== undefined) return said(data["output"]);
  return typeof data["summary"] === "string" ? data["summary"] : "nothing";
}

function said(value: unknown): string {
  return typeof value === "string" ? value : (JSON.stringify(value, null, 2) ?? String(value));
}
