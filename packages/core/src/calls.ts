/** Call view model for supervisor apps: status, waiting, duration and participants. */

import { type SessionLine } from "./wire/rest.js";
import { type State } from "./wire/state.js";

/** Placeholder for a missing value. */
export const NOTHING = "—";

/** Ringing, dialling or connected. */
export function isLive(line: Pick<SessionLine, "status">): boolean {
  return line.status !== "ended";
}

// Widget chat also uses a LiveKit room, so check the caller's `pinecall.scope` attribute instead.
/** Whether the call has audio: a room whose caller is not on a `chat` token. */
export function isSpoken(state: Pick<State, "room">): boolean {
  const room = state.room;
  if (room === null) return false;
  const caller = room.participants.find((participant) => participant.identity === room.caller);
  return caller?.attributes["pinecall.scope"] !== "chat";
}

/** Live call with an open attention request. */
export function wantsAPerson(line: SessionLine): boolean {
  return isLive(line) && line.attention?.status === "open";
}

/** Elapsed time since a unix timestamp, formatted `m:ss` or `h:mm:ss`. */
export function elapsed(since: number | null, now: number = Date.now() / 1000): string {
  if (since === null) return NOTHING;
  const total = Math.max(0, Math.round(now - since));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = String(total % 60).padStart(2, "0");
  return hours > 0 ? `${hours}:${String(minutes).padStart(2, "0")}:${seconds}` : `${minutes}:${seconds}`;
}

/** Format +1, +34 and +598 numbers; others unchanged. */
export function prettyNumber(number: string | null | undefined): string {
  if (number === null || number === undefined) return NOTHING;
  const digits = number.replace(/[^\d]/g, "");
  if (number.startsWith("+1") && digits.length === 11) return `+1 (${digits.slice(1, 4)}) ${digits.slice(4, 7)}-${digits.slice(7)}`;
  if (number.startsWith("+34") && digits.length === 11) return `+34 ${digits.slice(2, 5)} ${digits.slice(5, 8)} ${digits.slice(8)}`;
  if (number.startsWith("+598") && digits.length === 11) return `+598 ${digits.slice(3, 5)} ${digits.slice(5, 8)} ${digits.slice(8)}`;
  return number;
}

/**
 * Short id (4 chars) for a `web_…` or `call_…` address (widget visitor or console Chat), else null.
 * The app supplies the surrounding label.
 */
export function visitorId(address: string | null | undefined): string | null {
  if (address === null || address === undefined) return null;
  const id = address.startsWith("web_") ? address.slice(4) : address.startsWith("call_") ? address.slice(5) : null;
  return id === null || id === "" ? null : id.slice(0, 4);
}

// Takes four fields so a folded State can be passed too.
/** Display name for the other party: name, formatted number, `visitor(id)`, or the raw address. */
export function whoOn(line: Pick<SessionLine, "caller" | "direction" | "from" | "to">, visitor: (id: string) => string): string {
  const name = line.caller?.name;
  if (name !== null && name !== undefined && name !== "") return name;
  const from = line.direction === "outbound" ? line.to : line.from;
  if (from === null || from === undefined) return NOTHING;
  if (from.startsWith("+")) return prettyNumber(from);
  const id = visitorId(from);
  return id === null ? from : visitor(id);
}

/** A group of calls; calendar-day groups carry a timestamp to format the date from. */
export type CallDay<T> = { key: string; lines: T[] } & ({ name: "live" | "unstarted" } | { name: "today" | "yesterday" | "before"; at: number });

// `dayOf` is the app's: the console uses UTC, the phone its local calendar.
/** Group calls, keeping input order, under "live", their start day, or "unstarted". */
export function byDay<T extends Pick<SessionLine, "status" | "started_at">>(
  lines: readonly T[],
  dayOf: (at: number) => string,
  now: number = Date.now() / 1000,
): CallDay<T>[] {
  const today = dayOf(now);
  const yesterday = dayOf(now - 86400);
  const days: CallDay<T>[] = [];
  for (const line of lines) {
    const live = isLive(line);
    const key = live ? "live" : line.started_at === null ? "unstarted" : dayOf(line.started_at);
    let day = days.find((one) => one.key === key);
    if (day === undefined) {
      day =
        live || line.started_at === null
          ? { key, name: live ? "live" : "unstarted", lines: [] }
          : { key, name: key === today ? "today" : key === yesterday ? "yesterday" : "before", at: line.started_at, lines: [] };
      days.push(day);
    }
    day.lines.push(line);
  }
  return days;
}
