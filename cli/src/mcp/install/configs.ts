/** Somebody else's config file, with exactly one entry changed: Pinecall's. Their servers, settings and comments stay. */

import { copyFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";

import { PinecallError, errorMessage } from "../../errors.js";
import { SERVER, type Entry, type Host } from "./hosts.js";

/** Whether Pinecall is in the file already. An unreadable file counts as not: writing is where it is reported. */
export function registered(host: Host): boolean {
  if (!existsSync(host.file)) return false;
  const text = readFileSync(host.file, "utf8");
  if (host.format === "toml") return section(host.key).test(text);
  try {
    return SERVER in ((JSON.parse(text || "{}") as Record<string, Record<string, unknown> | undefined>)[host.key] ?? {});
  } catch {
    return false;
  }
}

/** Add or replace Pinecall's entry (null removes it), the file first copied beside itself as `.bak`. */
export function writeEntry(host: Host, entry: Entry | null): void {
  const before = existsSync(host.file) ? readFileSync(host.file, "utf8") : "";
  const after = host.format === "toml" ? inToml(before, host.key, entry) : inJson(before, host.file, host.key, entry);
  if (existsSync(host.file)) copyFileSync(host.file, `${host.file}.bak`);
  mkdirSync(dirname(host.file), { recursive: true });
  writeFileSync(host.file, after, "utf8");
}

// Replaced, never merged: a stale command from an older release is what re-running this repairs.
export function inJson(text: string, file: string, key: string, entry: Entry | null): string {
  let data: Record<string, unknown>;
  try {
    data = JSON.parse(text || "{}") as Record<string, unknown>;
  } catch (failed) {
    throw new PinecallError(`${file} is not valid JSON: fix it first (${errorMessage(failed)})`);
  }
  const servers = { ...((data[key] as Record<string, unknown> | undefined) ?? {}) };
  if (entry === null) delete servers[SERVER];
  else servers[SERVER] = entry;
  return `${JSON.stringify({ ...data, [key]: servers }, null, 2)}\n`;
}

// TOML is edited as text, one section up to the next `[`: parsing the whole file would drop its comments.
export function inToml(text: string, key: string, entry: Entry | null): string {
  const found = section(key);
  if (entry === null) return text.replace(found, "");
  const block = `[${key}.${SERVER}]\ncommand = ${JSON.stringify(entry.command)}\nargs = [${entry.args.map((one) => JSON.stringify(one)).join(", ")}]\n`;
  if (found.test(text)) return text.replace(found, block);
  return text.trim() === "" ? block : `${text.replace(/\n+$/, "")}\n\n${block}`;
}

function section(key: string): RegExp {
  const escaped = `${key}.${SERVER}`.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`^\\[${escaped}\\]\\n(?:(?!\\[).*\\n?)*`, "m");
}
