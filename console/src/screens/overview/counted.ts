/** The gateway's count of an agent's window read into what its Overview draws, and the newest calls worth a look. */

import { type SessionLine } from "@pinecall/core/wire/rest";

import { type InsightsDay, type WindowDays } from "../../lib/insights";

/** The doors a call comes in by, in the order every chart and legend lists them. */
export const CHANNELS = ["phone", "web", "whatsapp"] as const;
export type Channel = (typeof CHANNELS)[number];

/** One UTC day: its calls by channel, what they cost, and how the judges answered over them. */
export interface Day {
  day: string;
  calls: Record<Channel, number>;
  spend: number;
  held: number;
  judged: number;
}

// The list a reviewer opens first is short: the newest flagged calls, not all of them.
const WORTH_A_LOOK = 6;

/** The window's days as the charts draw them: the door answers one row per day, a quiet day included. */
export function daysOf(series: readonly InsightsDay[]): Day[] {
  return series.map((day) => ({
    day: day.day,
    calls: { phone: day.phone, web: day.web, whatsapp: day.whatsapp },
    spend: day.spend_usd,
    held: day.passed,
    judged: day.judged,
  }));
}

/** The newest calls a reviewer should open first: a person took part, a judge said no, or a promise went unrecorded. */
export function worthALook(lines: readonly SessionLine[]): SessionLine[] {
  return lines.filter((line) => (line.flags?.length ?? 0) > 0).slice(0, WORTH_A_LOOK);
}

/** How many calls a day took, every channel together. */
export function callsOn(day: Day): number {
  return CHANNELS.reduce((all, channel) => all + day.calls[channel], 0);
}

/** The window an Overview opens on when none was picked: today, else the last 7 days, else the last 30, the first that holds a call. */
export function windowWithCalls(month: readonly Day[]): WindowDays {
  const callsIn = (last: number): number => month.slice(-last).reduce((all, day) => all + callsOn(day), 0);
  if (callsIn(1) > 0) return 1;
  return callsIn(7) > 0 ? 7 : 30;
}
