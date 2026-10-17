/** The tools that hold the agent and look at it: `start`, `stop`, `status`, its `prompt`, and the `console_url`. */

import { z } from "zod";

import { serveStart } from "../../dev/child.js";
import { consoleLink } from "../../dev/start.js";
import { languageOf } from "../../project/language.js";
import { lentLine, lentTo } from "../agent-host/framework.js";
import { Held } from "../agent-host/held.js";
import { threadOnce } from "../agent-host/thread.js";
import { tool, ToolRefused } from "../tool.js";
import { AGENT } from "./fields.js";

export const start = tool({
  name: "start",
  description: "Hold the project's agent so it answers calls: in a thread of this server, reloaded on every save, or attached to a process already holding it.",
  schema: { agent: AGENT },
  manual:
    "`start` holds the agent the way `pinecall start` does: it answers written calls (`chat`), spoken ones from the console, and a phone ring when a number points at it. A TypeScript agent runs inside this server and reloads on every save; a project with nothing installed runs on the framework this server ships, lent to its thread alone — nothing is written into the project — until `npm install` pins its own, and `status` says so; a save that does not load keeps the version before answering, and `status` says why. A Ruby or Python agent is held by `pinecall start --watch` in a terminal: `start` then attaches to it. Already held on this machine (a terminal, another window), it attaches instead of fighting for the line. The console's screens reach the agent held here, through a companion this server keeps beside the thread.",
  handler: async (args, ctx) => {
    const home = ctx.agent("start", { agent: args.agent });
    const already = ctx.session.held.get(home.name);
    if (already !== undefined) return statusOf(already);
    // The gateway is asked before the thread starts, so a project with no key is refused by name.
    ctx.gateway();
    const held = new Held(ctx, home, ctx.session.beside);
    await held.start();
    ctx.session.held.set(home.name, held);
    return statusOf(held);
  },
});

export const stop = tool({
  name: "stop",
  description: "Stop holding the agent: its thread drains its live calls and leaves.",
  schema: { agent: AGENT },
  manual: "`stop` lets the agent go: a thread drains the calls it holds and leaves; an attached process is left running, since this server did not start it.",
  handler: async (args, ctx) => {
    const held = ctx.session.holding(args.agent);
    await held.stop();
    ctx.session.held.delete(held.home.name);
    return { stopped: held.home.name };
  },
});

export const status = tool({
  name: "status",
  description: "What this server holds: each agent, how (thread or attached), its app, the version answering, and why the newest save did not load.",
  schema: {},
  manual: "`status` leads with what is wrong, if anything: the sentence a save that does not load was refused with, or how the thread answering ended when it died. Otherwise each agent held, its app id and the version answering, and `framework` when the agent runs on the one this server lent the project.",
  handler: async (_args, ctx) => ({ held: [...ctx.session.held.values()].map(statusOf) }),
});

export const prompt = tool({
  name: "prompt",
  description: "Print the exact prompt the model reads when a call opens, or in a given state: offline, no key, no call.",
  schema: {
    agent: z.string().optional().describe("the agent's name; the project's only agent when left out"),
    state: z.record(z.string(), z.unknown()).optional().describe("fields of the class and their values, to see the prompt in that state"),
    channel: z.enum(["phone", "web", "whatsapp"]).optional().describe("the channel the prompt is written for"),
  },
  manual:
    "`prompt` prints what the model reads — the class's docstring, the rules, the tools, the view — exactly as a call would send it, offline. `state` sets fields first, so you can read the prompt at any stage. A Ruby or a Python agent's prompt is `pinecall prompt` in a terminal.",
  handler: async (args, ctx) => {
    const home = ctx.agent("prompt", { agent: args.agent });
    const language = languageOf(home.file);
    if (language !== "typescript") throw new ToolRefused(`a ${language === "ruby" ? "Ruby" : "Python"} agent's prompt is printed by its own language: \`pinecall prompt\` in a terminal`);
    const states = Object.entries(args.state ?? {}).flatMap(([field, value]) => ["--state", `${field}=${JSON.stringify(value)}`]);
    const flags = ["--file", home.file, "--slug", home.name, ...states, ...(args.channel === undefined ? [] : ["--channel", args.channel])];
    const lent = lentTo(home.root);
    const printed = await threadOnce(serveStart(undefined, home.file, "prompt", flags, { root: home.root, serve: lent?.entry }, ctx.processEnv), lent);
    if (printed.code !== 0) throw new ToolRefused(printed.err.trim() || `the prompt could not be printed (exit ${printed.code})`);
    return { agent: home.name, prompt: printed.out };
  },
});

export const consoleUrl = tool({
  name: "console_url",
  description: "A link that opens the console signed in, on the org's floor or on one agent: good for five minutes, once.",
  schema: { agent: z.string().optional().describe("open on this agent's screens; the org's floor when left out") },
  manual:
    "`console_url` answers a link for the person to open: the console signed in, its calls with every turn and verdict, its settings, a playground to talk to the agent by voice. The link carries a one-use code that dies in five minutes; it is the one value no answer hides.",
  reveals: (result) => [String((result as { url: string }).url)],
  handler: async (args, ctx) => ({ url: await consoleLink(ctx, args.agent), expires: "five minutes, one use" }),
});

function statusOf(held: Held): Record<string, unknown> {
  const lent = held.lent();
  return {
    agent: held.home.name,
    ...(held.broken === undefined ? {} : { broken: held.broken }),
    held: held.how(),
    app: held.app() ?? null,
    version: held.version,
    environment: held.ctx.env,
    // The version answering now: after an `npm install`, the next save runs on the project's own and the line goes.
    ...(lent === undefined ? {} : { framework: lentLine(lent) }),
  };
}
