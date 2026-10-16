/** Find, read and write a project's `.env` file. */

import { existsSync, readFileSync, writeFileSync } from "node:fs";
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

/**
 * Set these variables in the file: existing lines are replaced in place, new ones appended, other
 * lines untouched. A new file is created 0600 because it holds a key.
 */
export function writeDotenv(file: string, values: Record<string, string>): void {
  const lines = existsSync(file) ? readFileSync(file, "utf8").replace(/\n$/, "").split("\n") : [];
  const left = new Map(Object.entries(values));
  const written = lines.map((line) => {
    const name = line.trim().replace(/^export\s+/, "").split("=")[0]?.trim();
    const value = name === undefined ? undefined : left.get(name);
    if (name === undefined || value === undefined) return line;
    left.delete(name);
    return `${name}=${value}`;
  });
  for (const [name, value] of left) written.push(`${name}=${value}`);
  writeFileSync(file, `${written.join("\n")}\n`, { mode: 0o600 });
}

function unquoted(value: string): string {
  const quote = value[0];
  if ((quote === '"' || quote === "'") && value.length >= 2 && value.endsWith(quote)) return value.slice(1, -1);
  return value;
}
