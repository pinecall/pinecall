/** Load a tenant's agent file: register the TypeScript loader, import the class, read its source. */

import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

import { type Medium } from "../wire/defs.js";

import { Agent, setCall } from "../agent/agent.js";
import { describe } from "../agent/docstrings.js";
import { CallWorld } from "../call/call.js";
import { refuseTheEnvironment } from "../runtime/environment.js";

/** Thrown when what was asked cannot be served at all; the entry exits 2 with its sentence. */
export class CannotServe extends Error {
  override readonly name = "CannotServe";
}

/** A loaded agent class with its file path and source text. */
export interface Loaded {
  ctor: new () => Agent;
  file: string;
  source: string;
}

let registered = false;

/** Register tsx once per process, lazily, so tenant .ts/.tsx files load without a build step. */
async function useTypeScript(): Promise<void> {
  if (registered) return;
  const { register } = await import("tsx/esm/api");
  register();
  registered = true;
}

/**
 * Load an agent file and pass its source to `describe`. The source is required: the class
 * docstring and tool parameter types are not recoverable from the compiled module.
 */
export async function loadAgent(file: string): Promise<Loaded> {
  const path = resolve(file);
  if (!existsSync(path)) throw new CannotServe(`no agent at ${path}`);
  await useTypeScript();
  const module_ = (await import(pathToFileURL(path).href)) as { default?: unknown };
  const ctor = module_.default;
  if (typeof ctor !== "function") throw new CannotServe(`${path} has no default-exported Agent class`);
  const source = readFileSync(path, "utf8");
  describe(ctor, source, path);
  // Refuse environment fields on the instance here, since `prompt` never mounts.
  refuseTheEnvironment(new (ctor as new () => Agent)());
  return { ctor: ctor as new () => Agent, file: path, source };
}

/** Load the file served as `slug`; a class whose `static slug` says another is refused. */
export async function loadServed(file: string, slug: string): Promise<Loaded> {
  const loaded = await loadAgent(file);
  const declared = (loaded.ctor as { slug?: unknown }).slug;
  if (typeof declared === "string" && declared !== slug) {
    throw new CannotServe(`${loaded.file} says its slug is ${declared}, and it is served as ${slug}: the slug is its folder's name`);
  }
  return loaded;
}

/**
 * Instantiate the class with a stub call, since `render()` may read `this.call`. Without a
 * medium, the call's is the one its channel implies.
 */
export function instanceFor(loaded: Loaded, channel = "web", medium?: Medium): Agent {
  const agent = new loaded.ctor();
  const line = medium === undefined ? { id: "", contact: "", channel } : { id: "", contact: "", channel, medium };
  setCall(agent, new CallWorld(line, () => undefined));
  return agent;
}
