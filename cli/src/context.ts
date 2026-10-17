/** What a verb runs with: its IO, its env, and the project and gateway it asks for, resolved once on first use. */

import { GatewayClient, type Env } from "./api/client.js";
import { UsageError } from "./errors.js";
import { homeOf } from "./kit/home.js";
import type { IO } from "./kit/io.js";
import { anotherEnvsToken, NO_KEY, readCredentials, serverEnvOf, type Credentials } from "./project/credentials.js";
import { agentsOf, oneAgentOf, slugOf, type AgentChoice, type AgentHome } from "./project/layout.js";

/** What a verb runs with. Built once per invocation; a service takes it as its first argument. */
export interface Context {
  readonly io: IO;
  /** The process environment the verb and its children read. */
  readonly processEnv: NodeJS.ProcessEnv;
  /** Where the verb was typed: the project is looked for from here. */
  readonly cwd: string;
  /** Production with `--prod`, the sandbox otherwise. Set before the verb runs. */
  env: Env;
  /** Fires on Ctrl-C; a long verb passes it to what it waits on. */
  readonly signal: AbortSignal;
  /** The project's key and URL, or where they were not found. Never throws. */
  credentials(): Credentials;
  /** The gateway for this env; `UsageError` without a key or with a server token of the other env. */
  gateway(): GatewayClient;
  /** The agents a verb acts on, by `--file`/`--agent` or every one of the project. */
  agents(choice?: AgentChoice): AgentHome[];
  /** The one agent a conversational verb talks to: it must be in the project, its files are read. */
  agent(verb: string, choice?: AgentChoice): AgentHome;
  /** The slug a gateway verb acts on: `--agent` as typed, from any folder; else the project's one agent. */
  slug(verb: string, choice?: AgentChoice): string;
}

/** How a Context is made: the real process, or a test's buffers and folder. */
export interface ContextOptions {
  io: IO;
  processEnv?: NodeJS.ProcessEnv;
  cwd?: string;
  signal?: AbortSignal;
}

/** A Context over a process: nothing is read until a verb asks. */
export function createContext(options: ContextOptions): Context {
  return new ProcessContext(options);
}

class ProcessContext implements Context {
  readonly io: IO;
  readonly processEnv: NodeJS.ProcessEnv;
  readonly cwd: string;
  readonly signal: AbortSignal;
  env: Env = "sandbox";
  #credentials: Credentials | undefined;
  #gateway: GatewayClient | undefined;

  constructor(options: ContextOptions) {
    this.io = options.io;
    this.processEnv = options.processEnv ?? process.env;
    this.cwd = options.cwd ?? process.cwd();
    this.signal = options.signal ?? new AbortController().signal;
  }

  credentials(): Credentials {
    this.#credentials ??= readCredentials(this.processEnv, this.cwd, homeOf(this.processEnv));
    return this.#credentials;
  }

  gateway(): GatewayClient {
    if (this.#gateway !== undefined && this.#gateway.env === this.env) return this.#gateway;
    const { url, key } = this.credentials();
    if (key === undefined) throw new UsageError(NO_KEY);
    // A person's key opens both envs and the header says which; a server's token has one env.
    const token = serverEnvOf(key);
    if (token !== undefined && token !== this.env) throw new UsageError(anotherEnvsToken(token, url));
    this.#gateway = new GatewayClient(url, key, this.env);
    return this.#gateway;
  }

  agents(choice: AgentChoice = {}): AgentHome[] {
    return agentsOf(this.cwd, choice);
  }

  agent(verb: string, choice: AgentChoice = {}): AgentHome {
    return oneAgentOf(this.cwd, verb, choice);
  }

  slug(verb: string, choice: AgentChoice = {}): string {
    return slugOf(this.cwd, verb, choice);
  }
}

/** The first line a connecting verb says: gateway, key source and env. */
export function connectionLine(ctx: Context): string {
  const { url, source } = ctx.credentials();
  return `gateway ${url} · key from ${source} · ${ctx.env}`;
}
