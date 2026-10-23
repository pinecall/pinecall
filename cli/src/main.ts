#!/usr/bin/env node
/** The entry: the program is run, and every error becomes one sentence and an exit code. */

import { CommanderError } from "@commander-js/extra-typings";
import { realpathSync } from "node:fs";
import { pathToFileURL } from "node:url";

import { ZodError } from "zod";

import { createContext } from "./context.js";
import { Cancelled, errorMessage, PinecallError } from "./errors.js";
import { systemIO, type IO } from "./kit/io.js";
import { createProgram } from "./program.js";

// 0 did it · 1 what was measured did not hold · 2 it could not run (the arguments, the settings, a refusal, the network) · 130 stopped.
const CANNOT_RUN = 2;
// How long a verb gets to stop on its own after a signal before the signal takes its course.
const GRACE_MS = 1_500;

/** Run one invocation and answer its exit code. Nothing here calls `process.exit`. */
export async function main(
  argv: readonly string[],
  io: IO = systemIO(),
  processEnv: NodeJS.ProcessEnv = process.env,
  cwd: string = process.cwd(),
): Promise<number> {
  const stopping = new AbortController();
  const ctx = createContext({ io, processEnv, cwd, signal: stopping.signal });
  // A signal asks the verb to stop through the Context. A verb that does not listen (a plain fetch)
  // would hold the process: unless something else handles the signal (`start` passes it to its
  // child, which drains), the signal is raised again after a grace, with the default it had.
  const onSignal = (signal: NodeJS.Signals): void => {
    stopping.abort(new Cancelled());
    if (process.listenerCount(signal) > 1) return;
    setTimeout(() => {
      process.off(signal, onSignal);
      process.kill(process.pid, signal);
    }, GRACE_MS).unref();
  };
  process.on("SIGINT", onSignal);
  process.on("SIGTERM", onSignal);
  try {
    const program = await createProgram(ctx, argv);
    if (argv.length === 0) {
      program.outputHelp();
      return CANNOT_RUN;
    }
    await ctx.prepare();
    await program.parseAsync([...argv], { from: "user" });
    return stopping.signal.aborted ? new Cancelled().exit : 0;
  } catch (failed) {
    return exitWith(failed, io);
  } finally {
    process.off("SIGINT", onSignal);
    process.off("SIGTERM", onSignal);
  }
}

/** One sentence on stderr and the code: the only place an error is mapped to an exit. */
function exitWith(failed: unknown, io: IO): number {
  if (failed instanceof CommanderError) {
    // Help and version were printed by commander; a usage error was printed with the help.
    if (failed.code === "commander.helpDisplayed" || failed.code === "commander.version" || failed.code === "commander.help") return 0;
    return CANNOT_RUN;
  }
  if (failed instanceof Cancelled) return failed.exit;
  // An input a verb's schema refuses is the arguments' fault: its messages, one sentence.
  if (failed instanceof ZodError) {
    io.info(`pinecall: ${failed.issues.map((issue) => issue.message).join("; ")}`);
    return CANNOT_RUN;
  }
  if (failed instanceof PinecallError) {
    io.info(`pinecall: ${failed.message}`);
    return failed.exit;
  }
  if (failed instanceof Error && failed.name === "AbortError") return new Cancelled().exit;
  // Anything else — the network down, an answer that is no JSON — stopped the command from running.
  io.info(`pinecall: ${errorMessage(failed)}`);
  return CANNOT_RUN;
}

// Run when executed (dist/main.js as the published bin), not when imported.
const executed = process.argv[1] !== undefined && import.meta.url === pathToFileURL(realpathSync(process.argv[1])).href;
if (executed) process.exitCode = await main(process.argv.slice(2));
