/** `key=value` pairs as a repeated flag names them, each value read as JSON when it parses and as text otherwise. */

import { UsageError } from "../errors.js";

/** The pairs of a repeated `--<flag> key=value`, or undefined when the flag was not given; `flag` names it in a refusal. */
export function parseKeyValues(flag: string, items: readonly string[] | undefined): Record<string, unknown> | undefined {
  if (items === undefined) return undefined;
  const pairs: Record<string, unknown> = {};
  for (const item of items) {
    const at = item.indexOf("=");
    if (at <= 0) throw new UsageError(`--${flag} ${item} is not key=value: one keyword argument of the plugin, as the plugin names it`);
    pairs[item.slice(0, at)] = jsonOrText(item.slice(at + 1));
  }
  return pairs;
}

function jsonOrText(text: string): unknown {
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
}
