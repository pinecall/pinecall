/** The cases' list under its days, newest first, each day named the way Calls names it. */

import { utcDay } from "../lib/format";

export interface Day<T> {
  key: string;
  name: "today" | "yesterday" | "before";
  at: number;
  items: T[];
}

export function daysOf<T extends { at: number }>(items: readonly T[], now: number = Date.now() / 1000): Day<T>[] {
  const today = utcDay(now);
  const yesterday = utcDay(now - 86400);
  const days: Day<T>[] = [];
  for (const item of [...items].sort((one, other) => other.at - one.at)) {
    const key = utcDay(item.at);
    let day = days.find((one) => one.key === key);
    if (day === undefined) {
      day = { key, name: key === today ? "today" : key === yesterday ? "yesterday" : "before", at: item.at, items: [] };
      days.push(day);
    }
    day.items.push(item);
  }
  return days;
}
