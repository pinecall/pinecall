/** The one way a date, an amount, a duration, a count or a verdict's mark is written for a terminal. */

import { isAbsolute, relative } from "node:path";

/** The marks a check holds or breaks with. */
export const HELD = "✓";
export const BROKEN = "✗";
/** The mark a next step opens with: what to type, at the foot of an answer or under a refusal. */
export const NEXT = "→";

/** `  → pinecall x · pinecall y`: the next steps, one line at the foot of an answer, no backticks. */
export function formatHint(...steps: readonly string[]): string {
  return `  ${NEXT} ${steps.join(" · ")}`;
}

/**
 * A sentence and its next step as two lines: every sentence the CLI and the gateway write puts the
 * step after a colon, opening with a backticked command; the first colon such a command follows is
 * where the two lines part, and the backticks go. A sentence with no such colon stays one line.
 */
export function formatNotice(sentence: string): string[] {
  const at = sentence.indexOf(": `");
  if (at <= 0) return [sentence];
  return [sentence.slice(0, at), formatHint(sentence.slice(at + 2).replaceAll("`", ""))];
}

/**
 * A record in words, `stage ask · message.name Ana`: each field and its value, nested fields by
 * their path, a list joined by commas. What a person reads instead of the record's JSON.
 */
export function formatPairs(record: unknown, under = ""): string {
  if (record === null || typeof record !== "object" || Array.isArray(record)) return formatValue(record);
  const said = Object.entries(record as Record<string, unknown>).map(([name, value]) => {
    const path = under === "" ? name : `${under}.${name}`;
    return value !== null && typeof value === "object" && !Array.isArray(value) ? formatPairs(value, path) : `${path} ${formatValue(value)}`;
  });
  return said.filter((one) => one !== "").join(" · ");
}

function formatValue(value: unknown): string {
  if (Array.isArray(value)) return value.map(formatValue).join(", ");
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") return formatPairs(value);
  return String(value);
}

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

/** `3,483`, `20,500.5`, `0.8`: an amount as a column reads it, digits grouped, a fraction to one decimal. */
export function amount(n: number): string {
  return n.toLocaleString("en-US", { maximumFractionDigits: 1 });
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

/** A path as a person at `cwd` would type it: relative when it is under there, whole otherwise. */
export function pathFrom(cwd: string, path: string): string {
  const under = relative(cwd, path);
  if (under === "") return ".";
  return under.startsWith("..") || isAbsolute(under) ? path : under;
}

/** The text cut to `width` with an ellipsis, for a column. */
export function clipped(text: string, width: number): string {
  return text.length <= width ? text : `${text.slice(0, Math.max(0, width - 1))}…`;
}
