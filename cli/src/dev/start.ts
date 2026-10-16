/** `pinecall start` as a process: the serve entry started and watched, the companion connected, the lines printed until it leaves. */

import type { CamelEvent } from "@pinecall/agents/client";
import { z } from "zod";

import * as accounts from "../accounts/service/index.js";
import { countTools } from "../agents/service/index.js";
import type { Context } from "../context.js";
import { errorMessage, UsageError } from "../errors.js";
import { languageOf } from "../project/language.js";
import type { AgentHome } from "../project/layout.js";
import * as telephony from "../telephony/service.js";
import { line as describeLine } from "../telephony/render.js";
import { runOnce, serveStart, spawnServing, type Child } from "./child.js";
import { createCompanion, type Companion } from "./companion.js";
import { consoleAddress, consoleUrl, TALK, whyNoConsole } from "./console.js";
import * as render from "./render.js";
import { listenTo, live, plain, type PlainAgent, type Running } from "./screens.js";

/** What `start` takes: which agents, and how it shows them. */
export const StartInput = z.object({
  file: z.string().min(1).optional(),
  agent: z.string().min(1).optional(),
  showPrompt: z.boolean().default(false),
  events: z.boolean().default(false),
  ui: z.boolean().default(false),
  inspect: z.array(z.string()).default([]),
});
export type StartInput = z.infer<typeof StartInput>;

/** The agents' prompts through their serve entries, under each slug when there are several; no gateway. */
export async function showPrompts(ctx: Context, homes: AgentHome[]): Promise<number> {
  let worst = 0;
  for (const home of homes) {
    if (homes.length > 1) ctx.io.print(`── ${home.name} ──`);
    const args = ["--file", home.file, "--slug", home.name, "--show-machine"];
    worst = Math.max(worst, await runOnce(serveStart(undefined, home.file, "prompt", args, { root: home.root }, ctx.processEnv), ctx.io.stdout, ctx.io.stderr));
  }
  return worst;
}

/**
 * Start the agents' serve entry, wait for each to register, connect the companion that answers the
 * console, and stay up until the entry leaves. The same process in the sandbox and in production.
 */
export async function start(ctx: Context, input: StartInput): Promise<number> {
  // A single file, or every agents/<name>/ at a project's root (or the one named).
  const homes = ctx.agents({ file: input.file, agent: input.agent });
  const languages = new Set(homes.map((home) => languageOf(home.file)));
  if (languages.size > 1) throw new UsageError(`the agents of this project are in ${[...languages].join(" and ")}, and one process serves one language: add ${named(homes)}`);
  if (input.showPrompt) return await showPrompts(ctx, homes);
  if (input.ui && homes.length > 1) throw new UsageError(`the full-screen view watches one agent and this project has ${homes.length}: add ${named(homes)}`);
  // The org is resolved before anything registers, so a refusal comes first.
  let who: accounts.Whoami;
  try {
    who = await accounts.getWhoami(ctx);
  } catch (failed) {
    throw new UsageError(`\`pinecall start\` will not guess who this key is: ${errorMessage(failed)}`);
  }
  const args = [...homes.flatMap((home) => ["--file", home.file, "--slug", home.name]), "--events"];
  const first = homes[0]!;
  const child = spawnServing(serveStart(ctx.gateway(), first.file, "start", args, { root: first.root, inspect: input.inspect }, ctx.processEnv), { other: ctx.io.stderr, signals: process });
  // Before the registrations are read, so agent.registered is the first line of a pipe.
  if (input.events) child.onEvent((line) => ctx.io.stdout.write(`${JSON.stringify(line)}\n`));
  for (const home of homes) await child.registered(home.name);
  const companion = createCompanion(ctx, homes, child);
  try {
    await companion.pc.connect();
    const running: Running = { gone: Promise.race([child.exited, companionStopped(ctx, companion, child)]), leave: () => child.stop() };
    if (input.events) return await running.gone;
    if (input.ui) return await live(ctx.io, running, listenTo(child, first.name), { slug: first.name, url: ctx.gateway().url });
    const agents = await Promise.all(homes.map(async (home): Promise<PlainAgent> => plainAgent(ctx, home, child, who)));
    return await plain(ctx.io, running, agents, ctx.gateway().url);
  } finally {
    await companion.close();
    await child.stop();
  }
}

/** A signed-in console link: one-use, five minutes, so the key itself never travels; the page spends it for a key of its own. */
export async function consoleLink(ctx: Context, slug: string | undefined, screen = ""): Promise<string> {
  const gw = ctx.gateway();
  return consoleUrl(gw.url, gw.env, slug, await accounts.createLoginCode(ctx), screen);
}

async function plainAgent(ctx: Context, home: AgentHome, child: Child, who: accounts.Whoami): Promise<PlainAgent> {
  const { source } = ctx.credentials();
  return {
    slug: home.name,
    heard: listenTo(child, home.name),
    connected: render.connectedLine({ slug: home.name, url: ctx.gateway().url, tools: await countTools(ctx, home.name), org: accounts.orgOf(who), env: who.env, source }),
    after: () => linesOnceUp(ctx, home.name),
  };
}

// Printed after connect: the console, the agent's routes, and its line if it has a number. Routes come
// from the org's table, not the class. A failure prints a line; the agent keeps running.
async function linesOnceUp(ctx: Context, slug: string): Promise<string[]> {
  const routes = await telephony.listRoutes(ctx).catch(() => []);
  const said = [await talkLine(ctx, slug), render.routesLine(slug, routes)];
  if (routes.some((one) => one.agent === slug && one.number !== null)) {
    said.push(await telephony.showLine(ctx, { agent: slug }).then((line) => render.lineLine(describeLine(line)), (failed: unknown) => render.lineUnavailable(whyNoConsole(failed))));
  }
  return said;
}

/**
 * The link to the agent's chat in the console. Signed in only on a terminal: a process under pm2,
 * systemd or a hosted app writes stdout to a log others read later, and a code there is a way in.
 */
async function talkLine(ctx: Context, slug: string): Promise<string> {
  const gw = ctx.gateway();
  if (!ctx.io.tty) return render.talkLine(consoleAddress(gw.url, gw.env, slug, TALK), false);
  try {
    return render.talkLine(await consoleLink(ctx, slug, TALK), true);
  } catch (failed) {
    return render.talkUnavailable(whyNoConsole(failed));
  }
}

// An org member's Stop on the companion lets the console go; the agent's process is told to leave too.
async function companionStopped(ctx: Context, companion: Companion, child: Child): Promise<number> {
  await new Promise<void>((done) =>
    companion.pc.onStopped((why) => {
      ctx.io.info(why);
      done();
    }),
  );
  return await child.stop();
}

function named(homes: AgentHome[]): string {
  return homes.map((home) => `--agent ${home.name}`).join(" or ");
}

export type { CamelEvent };
