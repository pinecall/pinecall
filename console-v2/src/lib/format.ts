/** How numbers, days and durations are written across the console. */

export function money(value: number): string {
  return value >= 100 ? `$${Math.round(value)}` : `$${value.toFixed(2)}`;
}

export function percent(share: number): string {
  return `${Math.round(share * 100)}%`;
}

export function count(value: number): string {
  return value.toLocaleString("en-US");
}

/** `Nov 8`, from a UTC day `2026-11-08`. */
export function dayLabel(day: string): string {
  return new Date(`${day}T00:00:00Z`).toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
}

/** The UTC day a unix time falls on. */
export function utcDay(at: number): string {
  return new Date(at * 1000).toISOString().slice(0, 10);
}

/** `just now`, `6 min ago`, `3 h ago`, `2 d ago`. */
export function ago(at: number | null, now: number = Date.now() / 1000): string {
  if (at === null) return "—";
  const gone = Math.max(0, now - at);
  if (gone < 60) return "just now";
  if (gone < 3600) return `${Math.floor(gone / 60)} min ago`;
  if (gone < 86400) return `${Math.floor(gone / 3600)} h ago`;
  return `${Math.floor(gone / 86400)} d ago`;
}

/** A call's length, `3:07`. */
export function lengthOf(from: number | null, to: number | null): string {
  if (from === null || to === null) return "—";
  const total = Math.max(0, Math.round(to - from));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

/** A change against the window before, `+12%`, or null where there is nothing to compare with. */
export function change(now: number, before: number): number | null {
  return before === 0 ? null : (now - before) / before;
}
