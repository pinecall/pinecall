/** A live call as a supervisor's desk sees it: its transcript as it happens, and a move on it. */

import * as api from "../../api/calls.js";
import type { Context } from "../../context.js";
import { UsageError } from "../../errors.js";
import { callState } from "./sessions.js";

export type { Verb } from "../../api/calls.js";

const A_PAGE = 200;

/** Supervisor keys, one move per line. `q` leaves without ending the call. */
export const MOVES = [
  ["w <text>", "whisper to the agent — the caller never hears it"],
  ["s <text>", "say it to the caller, in the agent's voice, verbatim"],
  ["t", "take the line: the agent stops speaking and you are on it"],
  ["x", "give it back: the agent has the line again"],
  ["e [reason]", "end the call"],
  ["q", "leave the desk; the call goes on"],
] as const;

export const ALREADY_ENDED = (call: string): string => `${call} has ended, and a desk moves a call that is happening: \`pinecall sessions ${call}\` reads it`;

/** One entry of the call as a desk reads it. */
export type Seen =
  | { seq: number; caller: string }
  | { seq: number; agent: string }
  | { seq: number; tool: string; args: unknown }
  | { seq: number; desk: string; said: string | null }
  | { seq: number; ended: string };

/** What `watch` answered: the lines since the cursor, whether the call still goes, where to read on from. */
export interface Watched {
  call: string;
  live: boolean;
  lines: Seen[];
  next: number;
}

/** The call, live; one that ended is refused by name. */
export async function liveCall(ctx: Context, call: string): Promise<void> {
  const state = await callState(ctx, call);
  if (!state.live) throw new UsageError(ALREADY_ENDED(call));
}

/** A typed line as a verb, `leave` for q, or null when it is not a move. */
export function moveOf(typed: string): api.Verb | "leave" | null {
  const [key, ...rest] = typed.split(" ");
  const said = rest.join(" ").trim();
  if (key === "q") return "leave";
  if (key === "t") return { verb: "takeover" };
  if (key === "x") return { verb: "release" };
  if (key === "e") return { verb: "end", reason: said === "" ? undefined : said };
  if (said === "") return null;
  if (key === "w") return { verb: "whisper", text: said };
  if (key === "s") return { verb: "say", text: said };
  return null;
}

/** One move on a live call; it lands in the call's log as its own `supervisor.*` entry. */
export async function sendMove(ctx: Context, call: string, verb: api.Verb): Promise<{ call: string; sent: api.Verb }> {
  await api.sendVerb(ctx.gateway(), call, verb);
  return { call, sent: verb };
}

/** Each entry of the call from `after` on, as it is written, until `signal` aborts. */
export function followCall(ctx: Context, call: string, after: number, signal: AbortSignal): AsyncGenerator<api.Entry> {
  return api.followEntries(ctx.gateway(), { call }, { after, signal });
}

/**
 * What was said since `after`, read at once; a live call with nothing yet is followed on its stream
 * until something is said, the call ends or the wait is up. An ended one answers what is left.
 */
export async function watchCall(ctx: Context, call: string, after: number, waitS: number): Promise<Watched> {
  const state = await callState(ctx, call);
  let cursor = after;
  const lines: Seen[] = [];
  let ended = !state.live;
  const take = (entry: api.Entry): void => {
    cursor = entry.seq;
    if (entry.type === "call.ended") ended = true;
    const seen = seenOf(entry);
    if (seen !== undefined) lines.push(seen);
  };
  for (const entry of (await api.listCallEntries(ctx.gateway(), call, { after: cursor, limit: A_PAGE })).entries) take(entry);
  if (lines.length === 0 && !ended) {
    const stop = new AbortController();
    const deadline = setTimeout(() => stop.abort(), waitS * 1000);
    try {
      for await (const entry of followCall(ctx, call, cursor, stop.signal)) {
        take(entry);
        if (lines.length > 0 || ended) break;
      }
    } finally {
      clearTimeout(deadline);
      stop.abort();
    }
  }
  return { call, live: !ended, lines, next: cursor };
}

/** One log entry as the desk reads it; undefined for the entries a desk does not (metrics, state, scores). */
export function seenOf(entry: api.Entry): Seen | undefined {
  const data = entry.data;
  if (entry.type === "turn.user") return { seq: entry.seq, caller: String(data["text"] ?? "") };
  if (entry.type === "turn.agent") return { seq: entry.seq, agent: String(data["text"] ?? "") };
  if (entry.type === "tool.call") return { seq: entry.seq, tool: String(data["name"] ?? "?"), args: data["arguments"] ?? {} };
  if (entry.type === "call.ended") return { seq: entry.seq, ended: String(data["reason"] ?? "") };
  if (entry.type.startsWith("supervisor.")) {
    const said = data["text"] ?? data["reason"] ?? data["to"] ?? null;
    return { seq: entry.seq, desk: entry.type.slice("supervisor.".length), said: said === null ? null : String(said) };
  }
  return undefined;
}
