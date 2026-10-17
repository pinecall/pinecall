/** `pinecall setup`'s use cases: this machine as the runtime reads it, the build's vendors, where each key is, the answers as the runtime's flags, the runtime run. */

import { spawn, spawnSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

import { z } from "zod";

import { PinecallError } from "../errors.js";
import type { Credentials } from "../project/credentials.js";

export const NOT_INSTALLED =
  'pinecall-runtime is not installed on this machine: `uv tool install "pinecall-runtime[voice]"` (Python 3.12 or later, and Docker), then run this again';
/** Where a gateway on this machine answers: anything else is another host's. */
const THIS_MACHINE = new Set(["localhost", "127.0.0.1", "::1", "[::1]"]);
export const ANOTHER_HOST = (url: string, source: string): string =>
  `this project talks to ${url} (its key from ${source}): that runtime runs on another host, so this machine is neither scanned nor set up. Its models are that host's: \`pinecall-runtime setup\` there, or the console's providers.`;
/** The word for an open model on this machine, alone or before a model: `local`, `local/gemma4:12b`. */
export const LOCAL = "local";
export const STAGES = ["stt", "turn", "llm", "tts", "judge", "caller"] as const;
export const TURNS = ["stt", "smart-turn", "livekit"] as const;
/** The files a shell reads at start, where a person keeps `export DEEPGRAM_API_KEY=…`. */
const SHELL_FILES = [".zshrc", ".zprofile", ".bashrc", ".bash_profile", ".profile", join(".config", "fish", "config.fish")];
/** How a shell file names a key: `export X_API_KEY=…`, `X_API_KEY=…`, fish's `set -gx X_API_KEY …`. */
const A_KEY_LINE = /^\s*(?:export\s+|set\s+-g?x?\s+)?([A-Z][A-Z0-9_]*_API_KEY)\b/;

export type Stage = (typeof STAGES)[number];
export type Turn = (typeof TURNS)[number];

const CardSchema = z.object({ name: z.string(), memory_gib: z.number() });
const MachineSchema = z.object({
  system: z.string(),
  arch: z.string(),
  cores: z.number(),
  ram_gib: z.number(),
  cards: z.array(CardSchema),
  apple_silicon: z.boolean(),
  docker: z.boolean(),
  ollama_here: z.boolean(),
  keys_found: z.array(z.string()),
});
const CandidateSchema = z.object({
  model: z.string(),
  needs_gib: z.number(),
  fits: z.boolean(),
  short_by_gib: z.number(),
  first_token_s: z.number(),
  message: z.string(),
  documents: z.string(),
  talk: z.string(),
  note: z.string(),
});
const KeySchema = z.object({ vendor: z.string(), variable: z.string(), found: z.boolean() });
const RecommendationSchema = z.object({
  on: z.enum(["gpu", "apple", "cpu"]),
  budget_gib: z.number(),
  stack: z.record(z.string(), z.string()),
  candidates: z.array(CandidateSchema),
  keys: z.record(z.string(), KeySchema),
  notes: z.array(z.string()),
});
/** What `pinecall-runtime setup --recommend` answers. */
export const ReadSchema = z.object({ machine: MachineSchema, recommendation: RecommendationSchema });
/** One vendor of the build, as `pinecall-runtime providers installed --json` lists it. */
export const VendorSchema = z.object({ vendor: z.string(), does: z.array(z.string()), ends_turns: z.boolean(), broken: z.string().nullable() });

export type Card = z.infer<typeof CardSchema>;
export type Machine = z.infer<typeof MachineSchema>;
export type Candidate = z.infer<typeof CandidateSchema>;
export type Recommendation = z.infer<typeof RecommendationSchema>;
export type Read = z.infer<typeof ReadSchema>;
export type Vendor = z.infer<typeof VendorSchema>;

/** What the wizard ends with: one choice per stage, and the rest the runtime asks. */
export interface Answers {
  stt: string;
  turn: Turn;
  llm: string;
  tts: string;
  judge: string;
  caller: string;
  chatOnly: boolean;
  email?: string;
}

/** One thing a stage's picker offers. */
export interface Option {
  value: string;
  /** What it says beside the value: a vendor's stages, a model's measurements. */
  hint: string;
  /** Whether this machine can run it, where that is known. */
  fits?: boolean;
}

/** The gateway a project's own key points at, when it is not on this machine; undefined when setup is this machine's. */
export function anotherHost(credentials: Credentials): string | undefined {
  // No key, or the key setup itself handed over: the runtime is, or is about to be, this machine's.
  if (credentials.key === undefined || credentials.source.startsWith("the local runtime")) return undefined;
  const host = new URL(credentials.url).hostname;
  return THIS_MACHINE.has(host) ? undefined : credentials.url;
}

/** The runtime's reading of this machine and the stack it recommends. */
export function readMachine(env: NodeJS.ProcessEnv): Read {
  return ReadSchema.parse(JSON.parse(askRuntime(["setup", "--recommend"], env)));
}

/** The vendors this build runs, each with what it does; broken plugins left out. */
export function readVendors(env: NodeJS.ProcessEnv): Vendor[] {
  return z.array(VendorSchema).parse(JSON.parse(askRuntime(["--json", "providers", "installed"], env))).filter((one) => one.broken === null);
}

/** Which shell file names each `*_API_KEY`, by variable: the names alone, never a value. */
export function keysInShellFiles(home: string = homedir()): Record<string, string> {
  const found: Record<string, string> = {};
  for (const name of SHELL_FILES) {
    const path = join(home, name);
    if (!existsSync(path)) continue;
    for (const line of readFileSync(path, "utf8").split("\n")) {
      const variable = A_KEY_LINE.exec(line)?.[1];
      if (variable !== undefined && found[variable] === undefined) found[variable] = `~/${name}`;
    }
  }
  return found;
}

/** Where a vendor's key is: in the environment, in a shell file the runtime will not read, or nowhere. */
export function whereKeyIs(variable: string, env: NodeJS.ProcessEnv, inFiles: Record<string, string>): string {
  if ((env[variable] ?? "").trim() !== "") return "in the environment";
  const file = inFiles[variable];
  if (file !== undefined) return `in ${file}, not exported to this shell: \`source ${file}\` first, or the runtime asks`;
  return "not set: the runtime asks for it";
}

/** The answers the recommendation makes, each stage overridden by a flag that names it. */
export function answersFrom(read: Read, flags: Partial<Answers>): Answers {
  const stack = read.recommendation.stack;
  const llm = flags.llm ?? stack["llm"] ?? LOCAL;
  const turn = flags.turn ?? turnOf(stack["turn"]);
  return {
    stt: flags.stt ?? stack["stt"] ?? LOCAL,
    turn,
    llm,
    tts: flags.tts ?? stack["tts"] ?? LOCAL,
    judge: flags.judge ?? stack["judge"] ?? llm,
    caller: flags.caller ?? stack["caller"] ?? llm,
    chatOnly: flags.chatOnly ?? false,
    ...(flags.email === undefined ? {} : { email: flags.email }),
  };
}

/** A turn's name checked; a usage error names the three. */
export function turnOf(text: string | undefined): Turn {
  const named = (text ?? "smart-turn").trim().toLowerCase();
  if (!(TURNS as readonly string[]).includes(named)) throw new PinecallError(`--turn is one of ${TURNS.join(", ")}, not '${text}'`);
  return named as Turn;
}

/** The runtime's flags for the answers: `setup --yes --stt … --judge …`, the judge and the caller only when not the thinking's. */
export function flagsOf(answers: Answers): string[] {
  const flags = ["setup", "--yes", "--stt", answers.stt, "--turn", answers.turn, "--llm", answers.llm, "--tts", answers.tts];
  if (answers.judge !== answers.llm) flags.push("--judge", answers.judge);
  if (answers.caller !== answers.llm) flags.push("--caller", answers.caller);
  if (answers.chatOnly) flags.push("--chat-only");
  if (answers.email !== undefined) flags.push("--email", answers.email);
  return flags;
}

/** What a stage's picker offers on this machine: the open models measured, `local` itself, and every vendor doing the stage. */
export function optionsFor(stage: Stage, read: Read, vendors: Vendor[], sttVendor?: string): Option[] {
  if (stage === "turn") {
    const ears = vendors.find((one) => one.vendor === sttVendor);
    const turns: Option[] = [
      { value: "smart-turn", hint: "Smart Turn v3 reads the end of the turn off the audio, on the worker's CPU" },
      { value: "livekit", hint: "LiveKit's v1-mini, the same way" },
    ];
    if (ears?.ends_turns === true) turns.unshift({ value: "stt", hint: `${ears.vendor}'s own endpointing ends the turn` });
    return turns;
  }
  const modality = stage === "stt" || stage === "tts" ? stage : "llm";
  const local: Option[] =
    modality === "llm"
      ? read.recommendation.candidates.map((one) => ({
          value: `${LOCAL}/${one.model}`,
          hint: `${one.needs_gib} GB · first token ${one.first_token_s}s · message ${one.message} · documents ${one.documents} · talk ${one.talk}${one.fits ? "" : ` · short by ${one.short_by_gib} GB`}`,
          fits: one.fits,
        }))
      : [{ value: LOCAL, hint: modality === "stt" ? "Whisper large-v3-turbo on Speaches, on this machine" : "Kokoro on this machine" }];
  const theirs = vendors
    .filter((one) => one.does.includes(modality))
    .map((one) => ({ value: one.vendor, hint: `${one.does.join(", ")}${one.ends_turns ? " · ends the turn itself" : ""} · a key of yours` }));
  return [...local, ...theirs];
}

/** `pinecall-runtime <flags>` run with this terminal's streams until it stops; its exit code. */
export function runRuntime(flags: string[], env: NodeJS.ProcessEnv): Promise<number> {
  return new Promise((resolve, reject) => {
    const child = spawn("pinecall-runtime", flags, { stdio: "inherit", env });
    child.on("error", () => reject(new PinecallError(NOT_INSTALLED)));
    child.on("exit", (code) => resolve(code ?? 1));
  });
}

function askRuntime(flags: string[], env: NodeJS.ProcessEnv): string {
  const ran = spawnSync("pinecall-runtime", flags, { encoding: "utf8", env, timeout: 60_000 });
  if (ran.error !== undefined) throw new PinecallError(NOT_INSTALLED);
  if (ran.status !== 0) throw new PinecallError(`pinecall-runtime ${flags.join(" ")} failed: ${(ran.stderr || ran.stdout).trim().split("\n").at(-1) ?? ""}`);
  return ran.stdout;
}
