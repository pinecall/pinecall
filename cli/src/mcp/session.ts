/** One MCP server's state — the project it works in, what it holds, what is in flight — and the Context each tool call runs with. */

import { existsSync, statSync } from "node:fs";
import { join, resolve } from "node:path";

import type { SignIn } from "../accounts/service/index.js";
import { homeOf as pinecallHome } from "../kit/home.js";
import { readSession } from "../project/session.js";
import type { Env, GatewayClient } from "../api/client.js";
import { createContext, type Context } from "../context.js";
import { CollectingIO } from "../kit/io.js";
import { KEY_VARIABLE, readCredentials, type Credentials } from "../project/credentials.js";
import { slugOf, type AgentChoice, type AgentHome } from "../project/layout.js";
import { Held, type MakesBeside } from "./agent-host/held.js";
import type { SitePage } from "./site.js";
import { ToolRefused, type ToolContext } from "./tool.js";
import type { Talk } from "./tools/calls.js";
import type { InFlight } from "./tools/evals.js";
import type { LocalRuntimeProcess } from "./tools/runtime.js";

export const NO_PROJECT = "no project open: call `project` with action `open` and the folder's path, or `new` to write one";
export const NO_KEY_HERE = (root: string): string => `no key for ${root}: call \`login\`, and the person opens the link it answers`;
export const STOP_FIRST = (held: string[]): string => `stop the agents held first (${held.join(", ")}): a project is opened with nothing running`;

/** The agent a tool talks to: its slug, and the app and version when this server holds it in the env asked. */
export interface Reached {
  slug: string;
  app?: string | undefined;
  version?: number | undefined;
}

/** What a tool reads and changes across calls, for the life of one server. */
export class Session {
  /** The project folder the tools act on, once known. */
  root: string | undefined;
  signIn: SignIn | undefined;
  /** The agents this server holds, by slug. */
  readonly held = new Map<string, Held>();
  /** The written calls open, by call id. */
  readonly talks = new Map<string, Talk>();
  /** docs.pinecall.io's pages, read once. */
  site: Promise<SitePage[]> | undefined;
  /** A golden run, and a simulation, in flight by agent: each outlives one tool call. */
  readonly runs = new Map<string, InFlight>();
  readonly simulations = new Map<string, InFlight>();
  /** `pinecall-runtime setup`, when this server started it. */
  runtime: LocalRuntimeProcess | undefined;

  constructor(
    readonly processEnv: NodeJS.ProcessEnv,
    /** The roots the host declared, asked once and only when the host supports them. */
    private readonly declared: () => Promise<string[]>,
    /** What answers the console beside an agent held in a thread; the server's companion unless a test says otherwise. */
    readonly beside?: MakesBeside,
  ) {}

  /** The project's folder: one a tool opened, else the first the host declared, else the cwd when it holds agents/. */
  async project(): Promise<string> {
    if (this.root !== undefined) return this.root;
    const found = (await this.declared()).find(isProject) ?? (isProject(process.cwd()) ? process.cwd() : undefined);
    if (found === undefined) throw new ToolRefused(NO_PROJECT);
    this.root = found;
    return found;
  }

  /**
   * Open a folder as the project: it must exist. The server's cwd moves there, once, on the main
   * thread: a thread cannot, and a tenant's relative path must mean what it means under `pinecall start`.
   */
  open(path: string): string {
    const root = resolve(path);
    if (!existsSync(root) || !statSync(root).isDirectory()) throw new ToolRefused(`${root} is not a folder`);
    // The cwd is the held thread's too: it moves with nothing running.
    if (this.held.size > 0) throw new ToolRefused(STOP_FIRST([...this.held.keys()]));
    this.root = root;
    process.chdir(root);
    return root;
  }

  /** The Context one tool call runs with: the project's folder and key, in the env asked, its lines collected. */
  async contextFor(prod: boolean): Promise<ToolContext> {
    const root = await this.project().catch(() => undefined);
    const ctx = new SessionContext(this, root, prod ? "production" : "sandbox");
    if (root !== undefined) await ctx.prepare();
    return ctx;
  }

  /** The agent held, the one named or the only one; refused when none is. Only `stop` needs one. */
  holding(agent?: string): Held {
    if (agent !== undefined) {
      const named = this.held.get(agent);
      if (named === undefined) throw new ToolRefused(`${agent} is not held: call start`);
      return named;
    }
    const all = [...this.held.values()];
    if (all.length === 1) return all[0]!;
    throw new ToolRefused(all.length === 0 ? "no agent is held: call start" : `name the agent: one of ${[...this.held.keys()].join(", ")}`);
  }

  /**
   * What a tool that talks to the agent reaches, starting nothing: the copy this server holds when it
   * holds it in the env asked — a reload in flight awaited, a save that does not load refused — else
   * whoever holds the slug there: no app is named, and the gateway sends the call to the newest that takes it.
   */
  async reach(ctx: Context, agent: string | undefined): Promise<Reached> {
    const here = [...this.held.values()].filter((one) => one.ctx.env === ctx.env);
    const slug = agent ?? (here.length === 1 ? here[0]!.home.name : ctx.agent("this tool", {}).name);
    const held = this.held.get(slug);
    if (held !== undefined && held.ctx.env === ctx.env) return { slug, app: await held.ready(), version: held.version };
    return { slug };
  }

  /** Hang up every call and drain every thread: the server is closing. */
  async close(): Promise<void> {
    await Promise.allSettled([...this.talks.values()].map((talk) => talk.chat.end()));
    await Promise.allSettled([...this.held.values()].map((held) => held.stop()));
  }

  /** Every secret this session could print: the environment's key, the project's, and every key of the machine's sign-in, to be scrubbed from any answer. */
  secrets(): string[] {
    const exported = this.processEnv[KEY_VARIABLE];
    const project = this.root === undefined ? undefined : readCredentials(this.processEnv, this.root, pinecallHome(this.processEnv)).key;
    const machine = Object.values(readSession(pinecallHome(this.processEnv)).gateways).flatMap((one) => [one.key, ...Object.values(one.orgs ?? {})]);
    return [exported, project, ...machine].filter((one): one is string => one !== undefined && one !== "");
  }
}

/** A folder an agent lives in: it has `agents/`. */
export function isProject(folder: string): boolean {
  return existsSync(join(folder, "agents"));
}

/** A tool call's Context: a verb's, with the project's folder required wherever a key or an agent is asked for. */
class SessionContext implements ToolContext {
  readonly io = new CollectingIO();
  readonly signal = new AbortController().signal;
  readonly processEnv: NodeJS.ProcessEnv;
  readonly cwd: string;
  private readonly inner: Context;

  constructor(
    readonly session: Session,
    private readonly root: string | undefined,
    public env: Env,
  ) {
    this.processEnv = session.processEnv;
    this.cwd = root ?? process.cwd();
    this.inner = createContext({ io: this.io, processEnv: this.processEnv, cwd: this.cwd, signal: this.signal });
  }

  credentials(): Credentials {
    return this.inner.credentials();
  }

  async prepare(): Promise<void> {
    await this.inner.prepare();
  }

  gateway(): GatewayClient {
    if (this.root === undefined) throw new ToolRefused(NO_PROJECT);
    const { key, missing } = this.inner.credentials();
    if (key === undefined) throw new ToolRefused(missing === undefined ? NO_KEY_HERE(this.root) : missing.replaceAll("`pinecall login", "`login` (the tool), as `pinecall login"));
    this.inner.env = this.env;
    return this.inner.gateway();
  }

  agents(choice: AgentChoice = {}): AgentHome[] {
    if (this.root === undefined) throw new ToolRefused(NO_PROJECT);
    return this.inner.agents(choice);
  }

  agent(verb: string, choice: AgentChoice = {}): AgentHome {
    if (this.root === undefined) throw new ToolRefused(NO_PROJECT);
    const homes = this.inner.agents(choice);
    if (homes.length === 1) return homes[0]!;
    // A model is told the names, not a flag to type.
    throw new ToolRefused(`name the agent: one of ${homes.map((one) => one.name).join(", ")}`);
  }

  slug(verb: string, choice: AgentChoice = {}): string {
    if (choice.agent !== undefined || choice.file !== undefined) return slugOf(this.cwd, verb, choice);
    return this.agent(verb).name;
  }
}
