/** An agent the MCP server holds: in a thread of its own, or attached to the process that already holds it, and reloaded on a save. */

import { listApps } from "../../agents/service/index.js";
import type { Context } from "../../context.js";
import { createContext } from "../../context.js";
import { serveOne } from "../../dev/child.js";
import { createCompanion, isCompanion, MCP_COMPANION_SDK } from "../../dev/companion.js";
import { onSaves, Releases, SETTLES_MS, watchedFor } from "../../dev/reload.js";
import type { Serving } from "../../dev/serving.js";
import { hostname } from "../../kit/hostname.js";
import { StreamIO } from "../../kit/io.js";
import { languageOf } from "../../project/language.js";
import type { AgentHome } from "../../project/layout.js";
import { ToolRefused } from "../tool.js";
import { lentTo, type Lent } from "./framework.js";
import { Logs, threadServing, type Thread } from "./thread.js";

export const RUN_IT_YOURSELF = (language: string, root: string): string => `a ${language} agent is run by ${language}: \`pinecall start\` in ${root}, then call start again`;

/** What answers the console beside the thread: connected once the agent registered, closed with it. */
export interface Beside {
  connect(): Promise<void>;
  close(): Promise<void>;
}

/** Makes the companion beside a held agent; the server's is the CLI's own companion, a test's is nothing. */
export type MakesBeside = (ctx: Context, home: AgentHome, serving: Serving) => Beside;

export const companionBeside: MakesBeside = (ctx, home, serving) => {
  const companion = createCompanion(ctx, [home], serving, MCP_COMPANION_SDK);
  return { connect: () => companion.pc.connect(), close: () => companion.close() };
};

/** One agent held: who serves its calls, which version, and why the newest save did not load if it did not. */
export class Held {
  readonly logs = new Logs();
  /** The held agent's own context: its env and gateway, its lines kept in the logs, never on the protocol's stdout. */
  readonly ctx: Context;
  private releases: Releases<Thread> | undefined;
  private attached: string | undefined;
  private unwatch: (() => void) | undefined;
  private companion: Beside | undefined;
  // Set while `stop` drains the thread: its exit then is the one asked for, never a death.
  private stopping = false;

  constructor(
    asked: Context,
    readonly home: AgentHome,
    private readonly beside: MakesBeside = companionBeside,
    private readonly settlesMs = SETTLES_MS,
  ) {
    this.ctx = createContext({ io: new StreamIO(this.logs.stream(), this.logs.stream()), processEnv: asked.processEnv, cwd: home.root });
    this.ctx.env = asked.env;
  }

  /** The version answering; 0 when no thread runs here. */
  get version(): number {
    return this.releases?.version ?? 0;
  }

  /** The load's own sentence when the newest save does not load, or how the thread answering died; the version before keeps answering. */
  get broken(): string | undefined {
    return this.releases?.broken;
  }

  /** The app id the agent's calls reach, held here or found. */
  app(): string | undefined {
    return this.attached ?? this.releases?.current.app(this.home.name);
  }

  /** Whether this server runs the agent itself or talks to a process somebody else started. */
  how(): "thread" | "attached" | "stopped" {
    if (this.attached !== undefined) return "attached";
    return this.releases === undefined ? "stopped" : "thread";
  }

  /** Attach to a process of this machine already holding the slug, else start a thread (TypeScript only) and watch the folder. */
  async start(): Promise<void> {
    const found = await appOnThisMachine(this.ctx, this.home.name);
    if (found !== undefined) {
      this.attached = found;
      return;
    }
    const language = languageOf(this.home.file);
    if (language !== "typescript") throw new ToolRefused(RUN_IT_YOURSELF(language === "ruby" ? "Ruby" : "Python", this.home.root));
    this.releases = new Releases(await this.started(), () => this.started(), ({ version, broken }) => {
      if (broken === undefined) this.logs.add(`── version ${version} answering`);
    });
    // The console's screens reach the agent this server holds, through whichever thread answers now:
    // a reload changes the app, not the companion.
    this.companion = this.beside(this.ctx, this.home, this.serving());
    await this.companion.connect();
    const releases = this.releases;
    this.unwatch = onSaves(watchedFor([this.home]), () => void releases.reload(), this.settlesMs);
  }

  /** Every tool that talks to the agent awaits a reload in flight first, then refuses with the load's sentence if the save broke it. */
  async ready(): Promise<string> {
    // The process a terminal holds reloads on its own saves, under a new app each time: the app is
    // asked again, or every tool after a save was refused "does not hold agent" (P F2, 2026-10-24).
    if (this.attached !== undefined) {
      const found = await appOnThisMachine(this.ctx, this.home.name);
      if (found === undefined) throw new ToolRefused(`${this.home.name} is no longer held on this machine: call start`);
      this.attached = found;
    }
    await this.releases?.settled();
    if (this.broken !== undefined) throw new ToolRefused(`the newest save does not load, so nothing was asked of the version before: ${this.broken}`);
    const app = this.app();
    if (app === undefined) throw new ToolRefused(`${this.home.name} is not held: call start`);
    return app;
  }

  /** The framework lent to the version answering now, when the project installed none. */
  lent(): Lent | undefined {
    return this.releases?.current.lent;
  }

  /** Drain the thread and stop watching; an attached process is left as it was. */
  async stop(): Promise<void> {
    this.stopping = true;
    this.unwatch?.();
    this.unwatch = undefined;
    const releases = this.releases;
    await releases?.close();
    await this.companion?.close();
    this.companion = undefined;
    this.attached = undefined;
    this.releases = undefined;
    if (releases !== undefined) await releases.current.stop();
  }

  // The companion reads the app on every dial: the thread answering now, never the one it started with.
  private serving(): Serving {
    return {
      app: () => this.app(),
      registered: async () => await this.ready(),
      configured: async () => void (await this.ready()),
      onEvent: () => () => undefined,
    };
  }

  private async started(): Promise<Thread> {
    // A project nobody installed yet runs on the framework this server ships, until an install pins its own.
    const lent = lentTo(this.home.root);
    const thread = threadServing(serveOne(this.ctx.gateway(), this.home, { console: false, serve: lent?.entry }, this.ctx.processEnv), this.logs, undefined, lent);
    try {
      await thread.registered(this.home.name);
      await thread.configured(this.home.name);
    } catch (failed) {
      await thread.stop();
      throw failed;
    }
    // A thread that dies later (a tool or a hook throwing where nothing catches it) leaves no app behind:
    // every call to it would wait out its timeout. While it is the one answering, its death is the
    // sentence `status` leads with and every tool refuses with, until a save loads a version that lives.
    void thread.exited.then((code) => {
      if (this.releases?.current === thread && !this.stopping) this.releases.broken = died(code, this.logs.last(5));
    });
    return thread;
  }
}

/** Why the thread answering is gone: its exit code and the last lines it printed, the stack among them. */
export function died(code: number, lines: string[]): string {
  return `the agent's thread ended (exit ${code}), so nothing answers its calls; save a fix to load it again: ${lines.join(" · ") || "no line said why"}`;
}

/** The app of this machine already holding the slug — the agent's own process, never a companion — so two windows never fight for the line. */
export async function appOnThisMachine(ctx: Context, slug: string): Promise<string | undefined> {
  const apps = await listApps(ctx);
  return apps.find((one) => one.agents.includes(slug) && one.host === hostname() && one.holder !== null && !isCompanion(one.sdk))?.app;
}
