/** A call's log read for a benchmark: its lines against its recording's clock, each reply's seconds, what went unpriced, and why it may not count. */

import type { Entry, Row } from "./calls.js";
import type { Line, NotCounted } from "./scorecard.js";

/** The entries a benchmark reads of a call's log. */
export const READ = ["agent.state", "turn.user", "turn.agent", "tool.call", "tool.result", "error", "call.summary"] as const;

// What a tool answered is shown under its call: enough to read what the agent was given, not a page of it.
const A_TOOL_ANSWER_SHOWS = 260;

const numberIn = (from: unknown, name: string): number | null => {
  const value = (from as Record<string, unknown> | undefined)?.[name];
  return typeof value === "number" ? value : null;
};

/** The call's summary, when its log has one. */
function summaryOf(entries: readonly Entry[]): Record<string, unknown> | null {
  return entries.find((entry) => entry.type === "call.summary")?.data ?? null;
}

// The gateway does not say when a call's recording began (2026-11). The session starts its recorder as
// it starts, and the log's first `agent.state` was measured within 0.3 s of it on six calls: the lines
// are placed by that, and a call with none by its first entry. A summary that carries
// `recording_started_at` is believed over both, for the day the gateway says it.
/** When the recording began, by the log's clock, and whether the gateway said so itself. */
export function recordingBegan(entries: readonly Entry[], startedAt: number): { at: number; said: boolean } {
  const said = numberIn(summaryOf(entries), "recording_started_at");
  if (said !== null) return { at: said, said: true };
  return { at: entries.find((entry) => entry.type === "agent.state")?.ts ?? startedAt, said: false };
}

/** What was said and done on the call, each with the second of its recording it begins at. */
export function linesOf(entries: readonly Entry[], began: number): Line[] {
  const lines: (Line & { id?: unknown })[] = [];
  const at = (second: number): number => Math.round(Math.max(second - began, 0) * 100) / 100;
  for (const entry of entries) {
    const data = entry.data;
    const ts = entry.ts ?? began;
    if (entry.type === "turn.user" || entry.type === "turn.agent") {
      const text = data["text"];
      if (typeof text !== "string" || text === "") continue;
      const starts = numberIn(data["metrics"], "started_speaking_at") ?? ts;
      const stops = numberIn(data["metrics"], "stopped_speaking_at") ?? ts;
      lines.push({ who: entry.type === "turn.user" ? "caller" : "agent", text, at: at(starts), until: at(Math.max(stops, starts)), ...(data["interrupted"] === true ? { cut: true as const } : {}) });
    } else if (entry.type === "tool.call") {
      const given = Object.entries((data["arguments"] as Record<string, unknown> | undefined) ?? {}).map(([name, value]) => `${name}=${typeof value === "string" ? value : JSON.stringify(value)}`);
      lines.push({ who: "tool", text: `${String(data["name"])}(${given.join(", ")})`, at: at(ts), id: data["call_id"] });
    } else if (entry.type === "tool.result") {
      const called = [...lines].reverse().find((line) => line.who === "tool" && line.id === data["call_id"]);
      const output = data["output"];
      if (called !== undefined) called.gave = (typeof output === "string" ? output : JSON.stringify(output ?? null)).slice(0, A_TOOL_ANSWER_SHOWS);
    }
  }
  return lines.map(({ id: _id, ...line }) => line).sort((one, other) => one.at - other.at);
}

/** Each reply the call measured, in seconds: the caller's last word to the agent's first. */
export function repliesOf(entries: readonly Entry[]): number[] {
  return entries.flatMap((entry) => {
    const reply = entry.type === "turn.agent" ? numberIn(entry.data["metrics"], "e2e_latency") : null;
    return reply === null ? [] : [reply];
  });
}

/** The models the gateway priced nothing for on this call: its cost is then not what it cost. */
export function unpricedOf(entries: readonly Entry[]): string[] {
  const unpriced = (summaryOf(entries)?.["cost"] as { unpriced?: { model?: unknown }[] } | undefined)?.unpriced ?? [];
  return [...new Set(unpriced.flatMap((one) => (typeof one.model === "string" ? [one.model] : [])))];
}

// A gateway since 90c83b9b (2026-11-25) says it on the row (`valid`, `invalid`). One before it does not, and the
// same three faults are read off what it does say: a row that never started, a stage its vendor
// refused (the log's own `error`, in the vendor's words), a call that ended in error.
/** Why the call measured nothing of its agent, or null for one that counts. */
export function notCountedOf(row: Row, entries: readonly Entry[]): NotCounted | null {
  if (row.valid === false) return row.invalid ?? { kind: "platform", why: "the gateway says this call does not count" };
  if (row.valid === true) return null;
  if (row.why !== null) return { kind: "platform", why: `it never started: ${row.why}` };
  const errors = entries.filter((entry) => entry.type === "error").map((entry) => String(entry.data["message"] ?? "").split("\n")[0] ?? "");
  const refused = errors.find((message) => / refused this call/.test(message));
  if (refused !== undefined) return { kind: "vendor", why: refused };
  if (row.end_reason === "error") return { kind: "platform", why: errors[0] === undefined || errors[0] === "" ? "the call ended in error" : errors[0] };
  return null;
}
