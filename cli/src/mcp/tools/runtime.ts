/** The `runtime` tool: the runtime on this machine — what fits it, `pinecall-runtime setup` run from here, what it printed, and stopped. */

import { spawn, spawnSync, type ChildProcess } from "node:child_process";

import { z } from "zod";

import { homeOf } from "../../kit/home.js";
import { LOCAL_GATEWAY, readSignIn } from "../../project/session.js";
import { tool, ToolRefused } from "../tool.js";
import { WAIT, WAIT_S } from "./fields.js";

export const NO_RUNTIME =
  'pinecall-runtime is not installed on this machine: `uv tool install "pinecall-runtime[voice]"` (Python 3.12 or later, and Docker), then run this again';
/** `setup --recommend` arrived in pinecall-runtime 0.11.3; an older one answers argparse's own refusal. */
export const TOO_OLD = "this machine's pinecall-runtime is older than 0.11.3, the first with `setup --recommend`: `uv tool upgrade pinecall-runtime`, then run this again";
/** The line `setup` prints when the runtime answers and the processes are about to run. */
const READY = "ready";
/** How many of the runtime's lines an answer carries. */
const LAST_LINES = 40;
/** How long `down` gives `setup` to stop its gateway and worker before giving up on it. */
const LEAVES_WITHIN_MS = 15_000;
/** The stages `up` takes as `setup` takes them, each a flag of the same name. */
const STAGES = ["stt", "turn", "llm", "tts", "judge", "caller"] as const;

/** `pinecall-runtime setup` as this server started it: its lines, whether it said ready, and how it ended. */
export interface LocalRuntimeProcess {
  child: ChildProcess;
  lines: string[];
  ready: boolean;
  exited: number | undefined;
}

const A_STAGE = (what: string): z.ZodOptional<z.ZodString> => z.string().optional().describe(`up: ${what} — local, local/<model>, or a vendor of yours; the stack that fits this machine when left out`);

export const runtime = tool({
  name: "runtime",
  description:
    "The runtime on this machine: `recommend` reads the machine and says the stack that fits it, `up` runs `pinecall-runtime setup` on that stack or the stages given (Docker, the schema, this machine signed in, open models), `status` says what it printed and whether it answers, `down` stops it.",
  schema: {
    action: z.enum(["status", "recommend", "up", "down"]).describe("status reads the runtime this server started, or the one `pinecall-runtime setup` left; recommend reads the machine and answers the stack that fits it, running nothing; up runs it and keeps it running; down stops it"),
    stt: A_STAGE("who hears the caller"),
    turn: z.enum(["stt", "smart-turn", "livekit"]).optional().describe("up: who ends the caller's turn — the ears' own endpointing, Smart Turn v3 or livekit's model; the one that fits the ears when left out"),
    llm: A_STAGE("who thinks"),
    tts: A_STAGE("who speaks"),
    judge: A_STAGE("who judges a finished call; the thinking's model when left out"),
    caller: A_STAGE("who plays the simulated caller; the thinking's model when left out"),
    models: z.enum(["local", "keys", "none"]).optional().describe("up: local runs every stage on this machine; keys runs deepgram, anthropic and cartesia; none leaves the providers row to the person; the stack that fits this machine when left out"),
    chat_only: z.boolean().optional().describe("up: written calls alone — no LiveKit, no worker, no ears, no voice; the cheapest first run"),
    email: z.string().optional().describe("up: who signs in to the console, the org's admin; admin@pinecall.local when left out"),
    wait_s: WAIT,
  },
  manual:
    "`runtime` is for a person who wants the runtime on their own machine, with no account; it needs pinecall-runtime 0.11.3 or newer on the machine, and an older one is refused naming the upgrade. Call `recommend` first: it reads the machine — its card or its Mac's memory and what is left for the models, Docker, the Ollama here and the models it holds, and where each vendor's key is (the environment or a shell file; never its value) — and answers the stack that fits it, each measured model with whether it fits and what it did. Show the person that stack and ask whether a stage should change; then `up` runs `pinecall-runtime setup --yes` on it, or on the stages given (`stt`, `turn`, `llm`, `tts`, `judge`, `caller`: `local`, `local/<model>` — any model Ollama holds — or a vendor). `up` brings Postgres, Redis and LiveKit up in Docker, writes the schema, makes the console's admin (`email`) with no password — none is made up where nobody is at a terminal: `pinecall-runtime orgs password default <email>` sets one in a terminal, and `console_url` opens the console signed in meanwhile — signs this machine in to the runtime in `~/.pinecall/session.json` (so `whoami`, `chat`, `test` and `start` work with no `login`) and pulls the local models once — minutes, the first time. A vendor's key is read from the environment or the person's shell files; one found nowhere refuses by name, and the person sets it in a terminal. `up` answers within `wait_s` with the lines printed so far; call `status` until a line says ready, then `whoami`. `down` stops the gateway, the worker and the services; the database and the sign-in are kept. A project made while the runtime runs here names it in its pinecall.json.",
  handler: async (args, ctx) => {
    const home = homeOf(ctx.processEnv);
    const started = ctx.session.runtime;
    if (args.action === "status") return statusOf(started, home);
    if (args.action === "recommend") {
      requireInstalled(ctx.processEnv);
      return recommended(ctx.processEnv);
    }
    if (args.action === "down") {
      if (started !== undefined && started.exited === undefined) await stopped(started);
      ctx.session.runtime = undefined;
      const down = spawnSync("pinecall-runtime", ["local", "down"], { encoding: "utf8", env: ctx.processEnv });
      return { stopped: true, said: lastLines((down.stdout + down.stderr).split("\n")), kept: "the database, and this machine signed in to it" };
    }
    if (started !== undefined && started.exited === undefined) return statusOf(started, home);
    requireInstalled(ctx.processEnv);
    const running = watched(spawn("pinecall-runtime", flagsOf(args), { stdio: ["ignore", "pipe", "pipe"], env: ctx.processEnv }));
    ctx.session.runtime = running;
    await readyOrTime(running, (args.wait_s ?? WAIT_S) * 1000);
    return statusOf(running, home);
  },
});

/** The `setup` line `up` runs: `--yes`, then a flag per stage or option given. */
export function flagsOf(args: { models?: string | undefined; chat_only?: boolean | undefined; email?: string | undefined } & Partial<Record<(typeof STAGES)[number], string | undefined>>): string[] {
  const flags = ["setup", "--yes"];
  for (const stage of STAGES) if (args[stage] !== undefined) flags.push(`--${stage}`, args[stage]);
  if (args.models !== undefined) flags.push("--models", args.models);
  if (args.chat_only) flags.push("--chat-only");
  if (args.email !== undefined) flags.push("--email", args.email);
  return flags;
}

function requireInstalled(env: NodeJS.ProcessEnv): void {
  const version = spawnSync("pinecall-runtime", ["--version"], { encoding: "utf8", env });
  if (version.error !== undefined || version.status !== 0) throw new ToolRefused(NO_RUNTIME);
}

/** What `pinecall-runtime setup --recommend` prints: the machine and the stack that fits it, as it says them. */
function recommended(env: NodeJS.ProcessEnv): unknown {
  const read = spawnSync("pinecall-runtime", ["setup", "--recommend"], { encoding: "utf8", env });
  if (read.status !== 0 && /invalid choice: 'setup'/.test(read.stderr)) throw new ToolRefused(TOO_OLD);
  if (read.status !== 0) throw new ToolRefused(`pinecall-runtime could not read this machine: ${lastLines((read.stderr + read.stdout).split("\n")).join(" ")}`);
  return JSON.parse(read.stdout) as unknown;
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
  const handed = readSignIn(home, LOCAL_GATEWAY);
  const key = handed === undefined ? { handed: false, says: "no runtime on this machine yet: call runtime with action recommend, then up" } : { handed: true, gateway: handed.url };
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
