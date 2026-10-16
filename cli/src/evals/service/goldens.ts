/** Golden files on the tenant's disk and the schema the runner accepts. */

import { existsSync } from "node:fs";
import { readdir, readFile, stat } from "node:fs/promises";
import { basename, extname, join, resolve, sep } from "node:path";

import { UsageError } from "../../errors.js";
import { DOCS_GOLDEN, MEMORY_GOLDEN } from "../../project/layout.js";

/** A fact of the tenant's backend, sent as the app's own `call.event` at its turn. */
export interface InjectedEvent {
  name: string;
  data?: Record<string, unknown>;
}

/** One step of what must follow a turn; each names itself by its one required key. */
export type Step =
  | { tool: string; args?: Record<string, unknown>; within_ms?: number }
  | { no_tool: string }
  | { reply: { says?: string[]; says_any?: string[]; not?: string[]; intent?: string; within_ms?: number } }
  | { end: "caller" | "agent" | "supervisor" | "platform" }
  | { nothing_else: true };

/** One input — a caller's line (`say`) or a backend's fact (`event`), exactly one — and what must follow it, in order. */
export interface Turn {
  say?: string;
  event?: InjectedEvent;
  then?: Step[];
}

/** What holds over the whole conversation; each field set is one check. */
export interface Expect {
  tools?: string[];
  not_tools?: string[];
  not?: string[];
  says?: string[];
  says_any?: string[];
  grounded?: boolean;
  register?: "tu" | "usted";
  /** Hang-up judges asked again of the golden's call, by name. */
  judges?: string[];
}

/** One scripted conversation: the state it opens in, its turns, and what holds at the end. */
export interface Golden {
  name: string;
  state?: Record<string, unknown>;
  turns: Turn[];
  /** Facts memory holds about the caller at call start, served to `recall` for this call only. */
  memory?: string[];
  /** `YYYY-MM-DD` the call opens on, so weekday references stay stable. */
  today?: string;
  expect?: Expect;
  /** Source call id when created by `runs promote`; not read by judges. */
  promoted_from?: string;
}

/**
 * What a path typed to `test` names: the file or folder when it is one, else a golden of the agent
 * by its name (`no-reserva-antes-del-si`, with or without `.json`); neither is refused by name.
 */
export function goldenPath(typed: string, goldens: string): string {
  if (existsSync(typed)) return typed;
  const named = join(goldens, typed.endsWith(".json") ? typed : `${typed}.json`);
  if (!typed.includes(sep) && existsSync(named)) return named;
  throw new UsageError(`no golden ${typed}: not a file here, nor one of ${goldens}`);
}

/** Every golden under the paths, sorted by file name; none for no paths. */
export async function goldensIn(paths: string[]): Promise<Golden[]> {
  const found: Golden[] = [];
  for (const path of paths) for (const file of await filesUnder(resolve(path))) found.push(...(await goldensOf(file)));
  return found;
}

/** The goldens in an agent's folder, or none when it does not exist. */
export async function goldensInFolder(folder: string): Promise<Golden[]> {
  return (await stat(folder).catch(() => null))?.isDirectory() === true ? await goldensIn([folder]) : [];
}

/** Goldens whose name contains `grep` (case-insensitive), or all when undefined. */
export function matching<T extends { name: string }>(found: T[], grep: string | undefined): T[] {
  if (grep === undefined) return found;
  const wanted = grep.toLowerCase();
  return found.filter((one) => one.name.toLowerCase().includes(wanted));
}

// A file holds one golden or a list; unnamed ones take the file's basename, numbered when there are several.
async function goldensOf(file: string): Promise<Golden[]> {
  const read = JSON.parse(await readFile(file, "utf8")) as unknown;
  const written = Array.isArray(read) ? (read as Golden[]) : [read as Golden];
  const stem = basename(file, extname(file));
  return written.map((one, index) => ({ ...one, name: one.name ?? (written.length > 1 ? `${stem} #${index + 1}` : stem) }));
}

// One level deep, sorted; the retrieval and recall goldens beside them are `docs eval`'s and `memory eval`'s.
async function filesUnder(path: string): Promise<string[]> {
  if (!(await stat(path).catch(() => null))?.isDirectory()) return [path];
  return (await readdir(path))
    .filter((name) => extname(name) === ".json" && name !== DOCS_GOLDEN && name !== MEMORY_GOLDEN)
    .sort()
    .map((name) => join(path, name));
}
