/** A JSON file named on the command line, read with errors that name the flag and the file. */

import { readFileSync } from "node:fs";

import { errorMessage, UsageError } from "../errors.js";

/** The parsed JSON of the file a flag names; a missing or unparseable file is a usage error naming both. */
export function readJsonFile<T>(flag: string, file: string): T {
  let text: string;
  try {
    text = readFileSync(file, "utf8");
  } catch (failed) {
    const why = (failed as NodeJS.ErrnoException).code === "ENOENT" ? "no such file" : errorMessage(failed);
    throw new UsageError(`${flag}: cannot read ${file} — ${why}`);
  }
  try {
    return JSON.parse(text) as T;
  } catch (failed) {
    throw new UsageError(`${flag}: ${file} is not JSON — ${errorMessage(failed)}`);
  }
}
