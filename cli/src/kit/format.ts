/** The one way a date, an amount, a duration, a count or a verdict's mark is written for a terminal. */

/** The marks a check holds or breaks with. */
export const HELD = "✓";
export const BROKEN = "✗";

/** `2026-10-16 14:05`, UTC, from epoch seconds; `-` for none. */
export function date(epochSeconds: number | null | undefined): string {
  if (epochSeconds === null || epochSeconds === undefined) return "-";
  return new Date(epochSeconds * 1000).toISOString().slice(0, 16).replace("T", " ");
}

/** `2026-10-16 14:05:09` from an ISO string or epoch seconds. */
export function timestamp(at: string | number): string {
  const when = typeof at === "number" ? new Date(at * 1000) : new Date(at);
  return when.toISOString().slice(0, 19).replace("T", " ");
}

/** `$0.0123`: four decimals, the precision a call's cost needs. */
export function money(usd: number | null | undefined): string {
  if (usd === null || usd === undefined) return "-";
  return `$${usd.toFixed(4)}`;
}

/** `1m 05s`, `12s`, `0.8s` from seconds. */
export function duration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "-";
  if (seconds < 10) return `${seconds.toFixed(1)}s`;
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round(seconds % 60);
  return `${minutes}m ${String(rest).padStart(2, "0")}s`;
}

/** `3 calls`, `1 call`: the noun agreed with the count. */
export function count(n: number, noun: string, plural: string = `${noun}s`): string {
  return `${n} ${n === 1 ? noun : plural}`;
}

/** `12.3 kB`, `4.0 MB` from bytes. */
export function bytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} kB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

/** `yes` / `no`. */
export function yesNo(value: boolean): string {
  return value ? "yes" : "no";
}

/** The text cut to `width` with an ellipsis, for a column. */
export function clipped(text: string, width: number): string {
  return text.length <= width ? text : `${text.slice(0, Math.max(0, width - 1))}…`;
}
