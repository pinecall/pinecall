/** Find and read a project's `.env` file. */

import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";

export const DOTENV = ".env";

/** The nearest `.env` from this directory up to the root, or undefined. */
export function nearestDotenv(from: string): string | undefined {
  for (let at = from; ; at = dirname(at)) {
    const file = join(at, DOTENV);
    if (existsSync(file)) return file;
    if (dirname(at) === at) return undefined;
  }
}

/**
 * Parse the common dotenv subset: `NAME=value`, optional `export ` prefix, matching quotes
 * stripped; `#` lines and lines without `=` are ignored.
 */
export function readDotenv(file: string): Record<string, string> {
  const found: Record<string, string> = {};
  for (const raw of readFileSync(file, "utf8").split(/\r?\n/)) {
    const line = raw.trim().replace(/^export\s+/, "");
    const equals = line.indexOf("=");
    if (line.startsWith("#") || equals <= 0) continue;
    found[line.slice(0, equals).trim()] = unquoted(line.slice(equals + 1).trim());
  }
  return found;
}

function unquoted(value: string): string {
  const quote = value[0];
  if ((quote === '"' || quote === "'") && value.length >= 2 && value.endsWith(quote)) return value.slice(1, -1);
  return value;
}
