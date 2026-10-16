/** A yes-or-no question asked of the person at the terminal, before something that cannot be undone. */

import type { IO } from "./io.js";
import { readLine } from "./stdin.js";

/** Asks `question` (ending in ` [y/N] `) and answers true on `y` or `yes`, in any case; anything else is no. */
export async function confirm(question: string, io: IO, input: NodeJS.ReadableStream = process.stdin): Promise<boolean> {
  const answer = await readLine(question, io, input);
  return /^y(es)?$/i.test(answer.trim());
}
