/** Which language an agent is written in, and the command that starts its serve entry. */

import { existsSync } from "node:fs";
import { createRequire } from "node:module";
import { basename, dirname, extname, join } from "node:path";

import { UsageError } from "../errors.js";

/** Accepted agent file names, in lookup order; the first that exists in a folder wins. */
export const AGENT_FILES = ["agent.tsx", "agent.ts", "agent.rb", "agent.py"] as const;

/** A language an agent may be written in. */
export type Language = "typescript" | "ruby" | "python";

/** The serve entry's two verbs. */
export type ServeVerb = "start" | "prompt";

const NO_FRAMEWORK = "this project does not install @pinecall/agents, which serves a TypeScript agent: npm i @pinecall/agents";

const inspectsNothing = (language: string): string => `--inspect attaches a Node debugger, and a ${language} agent runs no Node`;

/** How a serve entry is started beyond its verb's own arguments. */
export interface ServeOptions {
  /** The project root: its Gemfile, and the @pinecall/agents it installed, are looked for there. */
  root: string;
  /** Node's `--inspect…` flags, passed on to a TypeScript entry as they were typed. */
  inspect?: string[] | undefined;
  /** A TypeScript serve entry to run instead of the project's own: the one `pinecall mcp` lends a project that installed none. */
  serve?: string | undefined;
}

/** The language of an agent file, by its name. */
export function languageOf(file: string): Language {
  const name = basename(file);
  if (name === "agent.rb") return "ruby";
  if (name === "agent.py") return "python";
  return "typescript";
}

/** The command that runs a verb of a language's serve entry: the door rides in its env, never here. */
export function serveCommand(language: Language, verb: ServeVerb, args: string[], options: ServeOptions): string[] {
  const inspect = options.inspect ?? [];
  if (language === "python") {
    if (inspect.length > 0) throw new UsageError(inspectsNothing("Python"));
    return [pythonOf(options.root), "-m", "pinecall.serve", verb, ...args];
  }
  if (language === "ruby") {
    if (inspect.length > 0) throw new UsageError(inspectsNothing("Ruby"));
    const ruby = ["ruby", "-r", "pinecall", "-e", "exit Pinecall::Serve.main(ARGV)", "--", verb, ...args];
    return existsSync(join(options.root, "Gemfile")) ? ["bundle", "exec", ...ruby] : ruby;
  }
  const serve = options.serve ?? serveEntryOf(options.root);
  return [process.execPath, ...inspect, ...loaderFor(serve), serve, verb, ...args];
}

/**
 * The project's own `@pinecall/agents/serve`, so the framework serving its agents is the version
 * it pinned and never this CLI's. Found in the `node_modules` of the root or a folder above it, and
 * nowhere else: Node's resolution would also read `NODE_PATH`, which pnpm points at its own store.
 * Only resolved: the entry runs in the child, never in this process.
 */
export function serveEntryOf(root: string): string {
  for (let folder = root; ; folder = dirname(folder)) {
    const installed = join(folder, "node_modules", "@pinecall", "agents", "package.json");
    if (existsSync(installed)) return createRequire(installed).resolve("@pinecall/agents/serve");
    if (dirname(folder) === folder) throw new UsageError(NO_FRAMEWORK);
  }
}

/**
 * The project's own interpreter: the `.venv` that `uv sync` and `python -m venv` both make, so the
 * `pinecall` serving its agents is the one it pinned; `python3` on the PATH when it has none.
 */
export function pythonOf(root: string): string {
  const windows = process.platform === "win32";
  const venv = join(root, ".venv", windows ? "Scripts" : "bin", windows ? "python.exe" : "python");
  return existsSync(venv) ? venv : "python3";
}

/** Node flags to run a TypeScript entry from a checkout: this CLI's tsx; none for a built one. */
export function loaderFor(entry: string): string[] {
  return extname(entry) === ".ts" ? ["--import", import.meta.resolve("tsx")] : [];
}
