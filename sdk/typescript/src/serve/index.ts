/** `@pinecall/agents/serve`: the entry the CLI starts an agent with — `start` holds it, `prompt` prints it. */

import { realpathSync } from "node:fs";
import { pathToFileURL } from "node:url";

import { DeclarationRefused } from "../agent/tools.js";
import { Refused } from "../client/index.js";

import { processIo, type Io } from "./io.js";
import { CannotServe } from "./load.js";
import { prompt } from "./prompt.js";
import { start } from "./start.js";

const USAGE = `usage: serve start --file <agent.tsx> --slug <slug> [--file … --slug …] [--console] [--events]
       serve prompt --file <agent.tsx> --slug <slug> [--state field=json]… [--channel name] [--medium how] [--show-machine]

  Reads PINECALL_URL, PINECALL_KEY and PINECALL_ENV from its environment and nothing else.
  start leaves on SIGINT, SIGTERM or the end of its stdin, draining first; a second signal leaves now.`;

/** Run one verb; 2 when it cannot run at all, with the sentence on `err` — a flag it does not have,
 * a class it cannot serve, or a gateway that refuses the registration (a slug of another org). */
export async function main(argv: string[], io: Io = processIo()): Promise<number> {
  const [verb, ...rest] = argv;
  try {
    if (verb === "start") return await start(rest, io);
    if (verb === "prompt") return await prompt(rest, io);
  } catch (failed) {
    if (!(failed instanceof CannotServe) && !(failed instanceof DeclarationRefused) && !(failed instanceof Refused) && !isAFlag(failed)) throw failed;
    io.err.write(`${failed.message}\n`);
    return 2;
  }
  io.err.write(`${USAGE}\n`);
  return 2;
}

function isAFlag(failed: unknown): failed is Error {
  const code = (failed as NodeJS.ErrnoException).code;
  return failed instanceof Error && typeof code === "string" && code.startsWith("ERR_PARSE_ARGS_");
}

// argv[1] may be a symlink (a package's bin), so it is resolved before comparing.
function isEntry(): boolean {
  const entry = process.argv[1];
  if (entry === undefined) return false;
  try {
    return import.meta.url === pathToFileURL(realpathSync(entry)).href;
  } catch {
    return false;
  }
}

if (isEntry()) process.exitCode = await main(process.argv.slice(2));
