/** A flag's text as commander hands it, read into the value a service takes; a bad one is a usage error naming the flag. */

import { UsageError } from "../errors.js";

/** `--limit 20` as a number; undefined when the flag was left out. */
export function numberOf(flag: string, text: string | undefined): number | undefined {
  if (text === undefined) return undefined;
  const value = Number(text);
  if (text.trim() === "" || !Number.isFinite(value)) throw new UsageError(`${flag} takes a number, not ${text}`);
  return value;
}

/** `--types a.b,c.d` as a list, blanks dropped; undefined when the flag was left out. */
export function listOf(text: string | undefined): string[] | undefined {
  if (text === undefined) return undefined;
  return text
    .split(",")
    .map((one) => one.trim())
    .filter((one) => one !== "");
}
