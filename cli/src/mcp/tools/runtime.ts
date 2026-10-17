/** The `runtime` tool: the runtime on this machine — `pinecall-runtime setup` run from here, what it printed, and stopped. */

import { spawn, spawnSync, type ChildProcess } from "node:child_process";

import { z } from "zod";

import { homeOf } from "../../accounts/service/home.js";
import { readLocalRuntime } from "../../project/credentials.js";
import { tool, ToolRefused } from "../tool.js";
import { WAIT, WAIT_S } from "./fields.js";

export const NO_RUNTIME =
  'pinecall-runtime is not installed on this machine: `uv tool install "pinecall-runtime[voice]"` (Python 3.12 or later, and Docker), then call runtime again';
/** The line `setup` prints when the runtime answers and the processes are about to run. */
const READY = "ready";
/** How many of the runtime's lines an answer carries. */
const LAST_LINES = 40;
/** How long `down` gives `setup` to stop its gateway and worker before giving up on it. */
const LEAVES_WITHIN_MS = 15_000;

/** `pinecall-runtime setup` as this server started it: its lines, whether it said ready, and how it ended. */
export interface LocalRuntimeProcess {
  child: ChildProcess;
  lines: string[];
  ready: boolean;
  exited: number | undefined;
}

export const runtime = tool({
  name: "runtime",
  description:
    "The runtime on this machine: `up` runs `pinecall-runtime setup` (Docker, the schema, a key the CLI finds by itself, open models), `status` says what it printed and whether it answers, `down` stops it.",
  schema: {
    action: z.enum(["status", "up", "down"]).describe("status reads the runtime this server started, or the one setup left; up runs setup and keeps it running; down stops it"),
    models: z
      .enum(["local", "keys", "none"])
      .optional()
      .describe("up: local runs open models on this machine, no account (the default); keys reads the vendors' keys from the environment; none leaves the providers row"),
    chat_only: z.boolean().optional().describe("up: written calls alone — no LiveKit, no worker, no ears, no voice; the cheapest first run"),
    llm: z.string().optional().describe("up, with local models: the Ollama model to think with"),
    wait_s: WAIT,
  },
  manual:
    "`runtime` is for a person with no Pinecall account who wants the runtime on their own machine: `up` runs `pinecall-runtime setup --yes`, which brings Postgres, Redis and LiveKit up in Docker, writes the schema, hands a key to this CLI in `~/.pinecall/local.json` (so `whoami`, `chat`, `test` and `start` work with no `login` and no `link`) and, with local models, pulls Ollama, Whisper and Kokoro once — minutes, the first time. It answers within `wait_s` with the lines printed so far; call `status` until a line says ready, then `whoami`. `down` stops the gateway and the worker and the services; the database and the key are kept. A project with a key of its own (`.env`) keeps using it: the local runtime is read last.",
  handler: async (args, ctx) => {
    const home = homeOf(ctx.processEnv);
    const started = ctx.session.runtime;
    if (args.action === "status") return statusOf(started, home);
    if (args.action === "down") {
      if (started !== undefined && started.exited === undefined) await stopped(started);
      ctx.session.runtime = undefined;
      const down = spawnSync("pinecall-runtime", ["local", "down"], { encoding: "utf8", env: ctx.processEnv });
      return { stopped: true, said: lastLines((down.stdout + down.stderr).split("\n")), kept: "the database and the key in ~/.pinecall/local.json" };
    }
    if (started !== undefined && started.exited === undefined) return statusOf(started, home);
    requireInstalled(ctx.processEnv);
    const flags = ["setup", "--yes", ...(args.models === undefined ? [] : ["--models", args.models]), ...(args.chat_only ? ["--chat-only"] : []), ...(args.llm === undefined ? [] : ["--llm", args.llm])];
    const running = watched(spawn("pinecall-runtime", flags, { stdio: ["ignore", "pipe", "pipe"], env: ctx.processEnv }));
    ctx.session.runtime = running;
    await readyOrTime(running, (args.wait_s ?? WAIT_S) * 1000);
    return statusOf(running, home);
  },
});

function requireInstalled(env: NodeJS.ProcessEnv): void {
  const version = spawnSync("pinecall-runtime", ["--version"], { encoding: "utf8", env });
  if (version.error !== undefined || version.status !== 0) throw new ToolRefused(NO_RUNTIME);
}

function watched(child: ChildProcess): LocalRuntimeProcess {
  const running: LocalRuntimeProcess = { child, lines: [], ready: false, exited: undefined };
  const read = (chunk: Buffer): void => {
    for (const line of chunk.toString().split("\n")) {
      if (line === "") continue;
      running.lines.push(line);
      if (line.startsWith(READY)) running.ready = true;
    }
  };
  child.stdout?.on("data", read);
  child.stderr?.on("data", read);
  child.on("exit", (code) => {
    running.exited = code ?? 1;
  });
  return running;
}

function readyOrTime(running: LocalRuntimeProcess, ms: number): Promise<void> {
  return new Promise((done) => {
    const started = Date.now();
    const look = (): void => {
      if (running.ready || running.exited !== undefined || Date.now() - started >= ms) done();
      else setTimeout(look, 250);
    };
    look();
  });
}

async function stopped(running: LocalRuntimeProcess): Promise<void> {
  running.child.kill("SIGTERM");
  await new Promise<void>((done) => {
    const timer = setTimeout(() => {
      running.child.kill("SIGKILL");
      done();
    }, LEAVES_WITHIN_MS);
    running.child.once("exit", () => {
      clearTimeout(timer);
      done();
    });
  });
}

function statusOf(running: LocalRuntimeProcess | undefined, home: string): Record<string, unknown> {
  const handed = readLocalRuntime(home);
  const key = handed === undefined ? { handed: false, says: "no runtime on this machine yet: call runtime with action up" } : { handed: true, gateway: handed.url };
  if (running === undefined) return { running: false, ...key };
  return {
    running: running.exited === undefined,
    ready: running.ready,
    ...(running.exited === undefined ? {} : { exited: running.exited }),
    lines: lastLines(running.lines),
    ...key,
    ...(running.ready ? { says: "the runtime answers: whoami, then chat" } : running.exited === undefined ? { says: "still setting up: call status again" } : {}),
  };
}

function lastLines(lines: readonly string[]): string[] {
  return lines.filter((line) => line !== "").slice(-LAST_LINES);
}
