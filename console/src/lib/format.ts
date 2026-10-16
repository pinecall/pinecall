/** Formatting for durations, money, times (UTC) and percentages. */

import { type SessionLine } from "@pinecall/core/wire/rest";

import { NOTHING, isLive, visitorId, wantsAPerson } from "@pinecall/core/calls";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** Order: live calls waiting for a person, other live calls, ended calls. */
export function liveFirst(lines: SessionLine[]): SessionLine[] {
  const live = lines.filter(isLive);
  return [...live.filter(wantsAPerson), ...live.filter((line) => !wantsAPerson(line)), ...lines.filter((line) => !isLive(line))];
}

/** `1m 04s`, or a dash while the call is running. */
export function duration(line: { started_at: number | null; ended_at: number | null }): string {
  if (line.started_at === null || line.ended_at === null) return NOTHING;
  const total = Math.max(0, Math.round(line.ended_at - line.started_at));
  return `${Math.floor(total / 60)}m ${String(total % 60).padStart(2, "0")}s`;
}

/** `$0.0142`: four decimals, as a call often costs less than a cent. */
export function usd(value: number | null | undefined): string {
  return value === null || value === undefined ? NOTHING : `$${value.toFixed(4)}`;
}

/** `$1.65`. */
export function spend(value: number): string {
  return `$${value.toFixed(2)}`;
}

/** `15:10:47`, UTC. */
export function clockOf(at: number | null): string {
  if (at === null) return NOTHING;
  return new Date(at * 1000).toISOString().slice(11, 19);
}

/** `16 Sep, 15:10`, UTC. */
export function dayAndTime(at: number | null): string {
  if (at === null) return NOTHING;
  const date = new Date(at * 1000);
  return `${date.getUTCDate()} ${MONTHS[date.getUTCMonth()]}, ${date.toISOString().slice(11, 16)}`;
}

/** `16 Sep`, UTC. */
export function dayOf(at: number | null): string {
  if (at === null) return NOTHING;
  const date = new Date(at * 1000);
  return `${date.getUTCDate()} ${MONTHS[date.getUTCMonth()]}`;
}

/** `12 min ago`, `1 h ago`, `Yesterday`, or the day. */
export function ago(at: number | null, now: number = Date.now() / 1000): string {
  if (at === null) return NOTHING;
  const seconds = Math.max(0, now - at);
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} h ago`;
  if (seconds < 172800) return "Yesterday";
  return dayOf(at);
}

/** `YYYY-MM-DD`, UTC. */
export function utcDay(at: number): string {
  return new Date(at * 1000).toISOString().slice(0, 10);
}

export function today(now: number = Date.now() / 1000): { today: string; yesterday: string } {
  return { today: utcDay(now), yesterday: utcDay(now - 86400) };
}

export function startedOn(lines: readonly SessionLine[], day: string): SessionLine[] {
  return lines.filter((line) => line.started_at !== null && utcDay(line.started_at) === day);
}

/** `+18%`, `−4%`, or null when there is no baseline. */
export function change(now: number, before: number): { text: string; tone: "up" | "down" | "flat" } | null {
  if (before === 0) return null;
  const share = Math.round(((now - before) / before) * 100);
  if (share === 0) return { text: "steady", tone: "flat" };
  return share > 0 ? { text: `+${share}%`, tone: "up" } : { text: `−${Math.abs(share)}%`, tone: "down" };
}

/** `82%`. */
export function percent(share: number): string {
  return `${Math.round(share * 100)}%`;
}

/** Avatar letters when there is no name: "W" for web visitors, the last two digits for numbers. */
export function lettersFor(name: string | null | undefined, address: string | null | undefined): string | undefined {
  if (name !== null && name !== undefined && name !== "") return undefined;
  if (address === null || address === undefined) return undefined;
  if (address.startsWith("+")) return address.slice(-2);
  // Widget visitors and the console's Chat tab (whose caller address is the call id).
  return address.startsWith("web") || address.startsWith("call") ? "W" : undefined;
}

/** "Web visitor · 3f7d". */
export function webVisitor(id: string): string {
  return `Web visitor · ${id}`;
}

/** Label for a web visitor address, or null for any other address. */
export function visitorOf(address: string | null | undefined): string | null {
  const id = visitorId(address);
  return id === null ? null : webVisitor(id);
}
