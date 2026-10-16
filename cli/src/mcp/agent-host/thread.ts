/** An agent served in a worker thread of this process: the project's own serve entry, its `main` called with the thread's streams. */

import { PassThrough, Writable } from "node:stream";
import { pathToFileURL } from "node:url";
import { Worker } from "node:worker_threads";

import type { ServeStart } from "../../dev/child.js";
import { servingFrom, type Serving } from "../../dev/serving.js";
import { PinecallError } from "../../errors.js";
import type { Lent } from "./framework.js";

// A project that installed no framework is answered `@pinecall/agents` from the server's own, in this
// thread alone; whatever the project does install is asked first.
const LENDING = `
let from;
export function initialize(lent) { from = lent; }
export async function resolve(specifier, context, next) {
  try {
    return await next(specifier, context);
  } catch (failed) {
    if (specifier !== "@pinecall/agents" && !specifier.startsWith("@pinecall/agents/")) throw failed;
    return await next(specifier, { ...context, parentURL: from });
  }
}`;

// A thread is not a process: same pid, own module cache, ended with terminate(). Its stdin ending is
// the order to drain, as for the CLI's child; tsx is registered first when the entry is a checkout's .ts.
const ENTRY = `
const { workerData } = require("node:worker_threads");
const { EventEmitter } = require("node:events");
(async () => {
  if (workerData.lent !== undefined) require("node:module").register(workerData.lending, { data: workerData.lent });
  if (workerData.tsx !== undefined) (await import(workerData.tsx)).register();
  const { main } = await import(workerData.entry);
  process.exitCode = await main(workerData.argv, { out: process.stdout, err: process.stderr, env: process.env, input: process.stdin, signals: new EventEmitter() });
})();`;

/** Longer than a drain: the gateway's answer, then the tools still running. */
const LEAVES_WITHIN_MS = 40_000;

/** A tenant's leak ends its thread, not the server. */
export const CEILING_MB = 1024;

/** The last lines a thread printed, what a load that failed is told by: kept in memory, never written to stdout. */
export class Logs {
  readonly lines: string[] = [];
  constructor(private readonly keep = 500) {}

  add(text: string): void {
    for (const line of text.split("\n")) if (line.trim() !== "") this.lines.push(line);
    if (this.lines.length > this.keep) this.lines.splice(0, this.lines.length - this.keep);
  }

  last(count: number): string[] {
    return this.lines.slice(-count);
  }

  /** A stream whose lines land here: what a core writes for a terminal, kept off the protocol's stdout. */
  stream(): Writable {
    return new Writable({ write: (chunk: Buffer, _encoding, done) => (this.add(chunk.toString()), done()) });
  }
}

/** A serve entry this server started in a thread. */
export interface Thread extends Serving {
  /** The framework the server lent it, when the project installed none. */
  lent: Lent | undefined;
  /** Resolves with the exit code when the thread is gone; the sentence it died with is in the logs. */
  exited: Promise<number>;
  /** Ask it to drain and leave; terminated if it has not within the grace. Resolves when it is gone. */
  stop(): Promise<number>;
}

/** What a thread is started on: the serve entry's file and the argv after it, from the CLI's own `ServeStart`. */
export function threadArgs(start: ServeStart): { entry: string; argv: string[] } {
  const at = start.command.findIndex((word) => /[\\/]serve[\\/]index\.[jt]s$/.test(word));
  if (at < 0) throw new PinecallError("only a TypeScript agent is served in a thread: a Ruby or Python one is attached to the process that runs it");
  return { entry: start.command[at]!, argv: start.command.slice(at + 1) };
}

/** Start the serve entry in a thread and read its lines; its stderr and its non-entry lines go to the logs. */
export function threadServing(start: ServeStart, logs: Logs, registersWithinMs?: number, lent?: Lent): Thread {
  const worker = new Worker(ENTRY, {
    eval: true,
    ...onTheThread(start, lent),
    stdin: true,
    stdout: true,
    stderr: true,
    resourceLimits: { maxOldGenerationSizeMb: CEILING_MB },
  });
  const said = new PassThrough();
  said.on("data", (chunk: Buffer) => logs.add(chunk.toString()));
  worker.stderr.on("data", (chunk: Buffer) => logs.add(chunk.toString()));
  const serving = servingFrom(worker.stdout, said, registersWithinMs);
  const exited = new Promise<number>((done) => {
    worker.once("error", (failed: Error) => logs.add(failed.message.includes("memory") ? `the agent's thread passed its ${CEILING_MB} MB ceiling and was ended` : failed.message));
    worker.once("exit", (code) => done(code));
  });
  let stopping: Promise<number> | undefined;
  const stop = (): Promise<number> => {
    stopping ??= (async () => {
      const late = setTimeout(() => void worker.terminate(), LEAVES_WITHIN_MS);
      worker.stdin?.end();
      try {
        return await exited;
      } finally {
        clearTimeout(late);
      }
    })();
    return stopping;
  };
  return {
    ...serving,
    lent,
    registered: (slug) =>
      Promise.race([
        serving.registered(slug),
        exited.then((code) => Promise.reject(new PinecallError(`${slug} did not load (exit ${code}): ${logs.last(3).join(" · ") || "no line said why"}`))),
      ]),
    exited,
    stop,
  };
}

/** Run a serve entry's one-shot verb (`prompt`) in a thread to its end, and answer what it printed. */
export async function threadOnce(start: ServeStart, lent?: Lent): Promise<{ code: number; out: string; err: string }> {
  const worker = new Worker(ENTRY, { eval: true, ...onTheThread(start, lent), stdout: true, stderr: true });
  let out = "";
  let err = "";
  worker.stdout.on("data", (chunk: Buffer) => (out += chunk.toString()));
  worker.stderr.on("data", (chunk: Buffer) => (err += chunk.toString()));
  const code = await new Promise<number>((done) => {
    worker.once("error", (failed: Error) => ((err += failed.message), done(1)));
    worker.once("exit", done);
  });
  return { code, out, err };
}

// What the thread starts with: the entry and its argv, tsx for a checkout's .ts, and a lent framework's resolver and tsconfig.
function onTheThread(start: ServeStart, lent: Lent | undefined): { workerData: Record<string, unknown>; env: Record<string, string | undefined> } {
  const { entry, argv } = threadArgs(start);
  const tsx = entry.endsWith(".ts") ? import.meta.resolve("tsx/esm/api") : undefined;
  const lending = lent === undefined ? {} : { lent: lent.from, lending: `data:text/javascript,${encodeURIComponent(LENDING)}` };
  return {
    workerData: { entry: pathToFileURL(entry).href, argv, tsx, ...lending },
    // The project's tsconfig extends the framework it does not have: tsx reads the framework's own instead.
    env: lent === undefined ? start.env : { ...start.env, TSX_TSCONFIG_PATH: lent.tsconfig },
  };
}
