/** The goldens on the tenant's disk: a retrieval or recall golden's questions, and memory's extraction cases. */

import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { basename, extname, join, resolve } from "node:path";

import { UsageError } from "../../errors.js";
import { readJsonFile } from "../../kit/json-file.js";
import { DOCS_GOLDEN, isDirectory, MEMORY_GOLDEN } from "../../project/layout.js";

/** Where memory's extraction cases live, one written call each, and what is said when there are none. */
export const CASES = "agents/<name>/test/memory";
export const NO_CASES = `no extraction goldens at ${CASES}: write one, or name the file or directory to run`;

/** The questions of a golden file: a non-empty JSON list of the `shape` named in the refusal. */
export function questionsOf(golden: string, shape: string): unknown[] {
  if (!existsSync(golden)) throw new UsageError(`no golden at ${golden}: a JSON list of ${shape}`);
  const questions = readJsonFile<unknown>("the golden", golden);
  if (!Array.isArray(questions) || questions.length === 0) {
    throw new UsageError(`${golden} holds no questions: a golden is a JSON list of ${shape}`);
  }
  return questions;
}

/**
 * Every case under the paths. A file holds one case or a list; unnamed cases take the file's
 * basename, numbered when there are several. A folder is read one level deep, sorted, and the
 * retrieval and recall goldens beside the cases are skipped: `docs eval` and `memory eval` read those.
 */
export function casesIn<T extends { name?: string }>(paths: string[]): T[] {
  const found: T[] = [];
  for (const path of paths) for (const file of filesUnder(resolve(path))) found.push(...casesOf<T>(file));
  return found;
}

/** Cases whose name contains `grep` (case-insensitive), or all when undefined. */
export function matching<T extends { name: string }>(cases: T[], grep: string | undefined): T[] {
  if (grep === undefined) return cases;
  const wanted = grep.toLowerCase();
  return cases.filter((one) => one.name.toLowerCase().includes(wanted));
}

function casesOf<T extends { name?: string }>(file: string): T[] {
  const read = JSON.parse(readFileSync(file, "utf8")) as unknown;
  const written = Array.isArray(read) ? (read as T[]) : [read as T];
  const stem = basename(file, extname(file));
  return written.map((one, index) => ({
    ...one,
    name: one.name ?? (written.length > 1 ? `${stem} #${index + 1}` : stem),
  }));
}

function filesUnder(path: string): string[] {
  if (!isDirectory(path)) return [path];
  return readdirSync(path)
    .filter((name) => extname(name) === ".json" && name !== DOCS_GOLDEN && name !== MEMORY_GOLDEN)
    .sort()
    .map((name) => join(path, name));
}

/** Whether a path is there and is a file: a case named on the command line. */
export function isFile(path: string): boolean {
  return existsSync(path) && statSync(path).isFile();
}
