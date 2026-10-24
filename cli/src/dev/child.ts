/** The serve entry as a child process: started detached, its door in its env, told to leave once, killed if it does not. */

import { spawn, type ChildProcess } from "node:child_process";
import type { Writable } from "node:stream";

import type { GatewayClient } from "../api/client.js";
import { ProcessLeft, UsageError } from "../errors.js";
import type { AgentHome } from "../project/layout.js";
import { languageOf, serveCommand, type ServeOptions, type ServeVerb } from "../project/language.js";
import { servingFrom, type Serving } from "./serving.js";

/** What one serve entry is started with: the command, and the environment it reads its door from. */
export interface ServeStart {
  command: string[];
  env: Record<string, string | undefined>;
}

/**
 * The serve entry of the agent's language, for one verb, with the door in its environment and never
 * in its argv: an argv is read by every process on the machine. An offline verb is given no gateway.
 */
export function serveStart(gateway: GatewayClient | undefined, file: string, verb: ServeVerb, args: string[], options: ServeOptions, processEnv: NodeJS.ProcessEnv): ServeStart {
  const env = gateway === undefined ? { ...processEnv } : { ...processEnv, PINECALL_URL: gateway.url, PINECALL_KEY: gateway.key, PINECALL_ENV: gateway.env };
  return { command: serveCommand(languageOf(file), verb, args, options), env };
}

/**
 * The serve entry holding one agent, its lines on stdout: a console's process, which takes no call
 * it did not open, unless the calls it serves arrive naming no app (a spoken one, from a worker).
 */
export function serveOne(gateway: GatewayClient, agent: AgentHome, options: { console: boolean; inspect?: string[] | undefined; serve?: string | undefined }, processEnv: NodeJS.ProcessEnv): ServeStart {
  const args = ["--file", agent.file, "--slug", agent.name, ...(options.console ? ["--console"] : []), "--events"];
  return serveStart(gateway, agent.file, "start", args, { root: agent.root, inspect: options.inspect, serve: options.serve }, processEnv);
}

/** A serve entry this process started. */
export interface Child extends Serving {
  /** Resolves with the exit code when it is gone. */
  exited: Promise<number>;
  /** Ask it to leave (it drains), kill it if it has not within the grace; resolves when it is gone. */
  stop(): Promise<number>;
}

/** Longer than a drain: the gateway's answer, then the tools still running, 30 s at most. */
const LEAVES_WITHIN_MS = 40_000;

/** What starting a child may be given instead of the process's own. */
export interface SpawnOptions {
  /** Where the child's lines that are no entry go. */
  other: Writable;
  /**
   * Where SIGINT and SIGTERM are heard, for a verb that waits for the child to leave: the first is
   * passed on, the second kills. Without it this process dies as it would, and the child, its
   * stdin closed, leaves draining.
   */
  signals?: NodeJS.EventEmitter | undefined;
  graceMs?: number | undefined;
  registersWithinMs?: number | undefined;
}

const SIGNALS = ["SIGINT", "SIGTERM"] as const;

/**
 * Start a serve entry with `--events`. Detached, so a terminal's Ctrl-C reaches this process alone;
 * its stdin is a pipe whose end tells it this process is gone.
 */
export function spawnServing(start: ServeStart, options: SpawnOptions): Child {
  const [program, ...args] = start.command;
  const child = spawn(program!, args, { detached: true, stdio: ["pipe", "pipe", "inherit"], env: start.env });
  const serving = servingFrom(child.stdout!, options.other, options.registersWithinMs);
  const exited = exitOf(child);
  const stop = stopper(child, exited, options.graceMs ?? LEAVES_WITHIN_MS);
  if (options.signals !== undefined) passOn(options.signals, child, stop, exited);
  return {
    ...serving,
    registered: (slug) =>
      Promise.race([serving.registered(slug), exited.then((code) => Promise.reject(new ProcessLeft(`the agent's process left (exit ${code}) before ${slug} registered`, code || 1)))]),
    // The gateway's refusal of the declaration is the process's own last line, printed above this one.
    configured: (slug) =>
      Promise.race([serving.configured(slug), exited.then((code) => Promise.reject(new ProcessLeft(`the agent's process left (exit ${code}): the gateway did not take ${slug} as declared`, code || 1)))]),
    exited,
    stop,
  };
}

/** Run a serve entry to its end, its output into the streams given, as `prompt` does; resolves with its exit code. */
export function runOnce(start: ServeStart, out: Writable, err: Writable): Promise<number> {
  const [program, ...args] = start.command;
  const child = spawn(program!, args, { stdio: ["ignore", "pipe", "pipe"], env: start.env });
  child.stdout!.on("data", (chunk: Buffer) => out.write(chunk.toString()));
  child.stderr!.on("data", (chunk: Buffer) => err.write(chunk.toString()));
  return exitOf(child);
}

function passOn(signals: NodeJS.EventEmitter, child: ChildProcess, stop: () => Promise<number>, exited: Promise<number>): void {
  let heard = 0;
  const passedOn = (): void => {
    heard += 1;
    if (heard === 1) void stop();
    else child.kill("SIGKILL");
  };
  for (const signal of SIGNALS) signals.on(signal, passedOn);
  const unheard = (): void => {
    for (const signal of SIGNALS) signals.off(signal, passedOn);
  };
  exited.then(unheard, unheard);
}

function exitOf(child: ChildProcess): Promise<number> {
  return new Promise((done, refuse) => {
    child.once("error", (failed) => refuse(new UsageError(`${child.spawnfile} could not be started: ${failed.message}`)));
    child.once("exit", (code, signal) => done(code ?? (signal === null ? 1 : 128)));
  });
}

// One SIGTERM and the end of its stdin, then a kill after the grace; asked twice, the same promise.
function stopper(child: ChildProcess, exited: Promise<number>, graceMs: number): () => Promise<number> {
  let stopping: Promise<number> | undefined;
  return () => {
    stopping ??= (async () => {
      if (child.exitCode !== null || child.signalCode !== null) return await exited;
      const kill = setTimeout(() => child.kill("SIGKILL"), graceMs);
      child.kill("SIGTERM");
      child.stdin?.end();
      try {
        return await exited;
      } finally {
        clearTimeout(kill);
      }
    })();
    return stopping;
  };
}
