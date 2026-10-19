/** The command tree on one screen: the global flags, and one `register` call per domain. */

import { Command } from "@commander-js/extra-typings";

import type { Context } from "./context.js";
import { version } from "./version.js";

// Help's width when it is written to no terminal: a pipe, a file, a test.
const HELP_WIDTH = 80;

/** What every domain's `commands.ts` exports: it adds its verbs to the program, closing over the Context. */
export type Register = (program: Command, ctx: Context) => void;

// Order is the help order: first-day verbs first. Each domain imports only what its verbs need.
const DOMAINS: (() => Promise<{ register: Register }>)[] = [
  () => import("./scaffold/commands.js"),
  () => import("./accounts/commands.js"),
  () => import("./dev/commands.js"),
  () => import("./calls/commands.js"),
  () => import("./evals/commands/index.js"),
  () => import("./agents/commands.js"),
  () => import("./knowledge/commands.js"),
  () => import("./telephony/commands.js"),
  () => import("./billing/commands.js"),
  () => import("./judging/commands.js"),
  () => import("./providers/commands.js"),
  () => import("./hosting/commands.js"),
  () => import("./studio/commands.js"),
  () => import("./alerts/commands.js"),
  () => import("./mcp/commands.js"),
];

/** The whole CLI: `pinecall [--prod] [--json] <verb> …`, every domain's verbs registered. */
export async function createProgram(ctx: Context): Promise<Command> {
  const program = new Command("pinecall")
    .description("An agent's project in any language, against the Pinecall gateway.")
    .version(version(), "-v, --version")
    .option("--prod", "act in production for this one command (the sandbox otherwise)")
    .option("--json", "answer with one JSON object on stdout")
    .exitOverride()
    .configureOutput({
      writeOut: (text) => ctx.io.stdout.write(text),
      writeErr: (text) => ctx.io.stderr.write(text),
      // As wide as the terminal the help is written to (commander would read the process's own), 80 off one.
      getOutHelpWidth: () => ctx.io.columns ?? HELP_WIDTH,
      getErrHelpWidth: () => ctx.io.columns ?? HELP_WIDTH,
    })
    .showHelpAfterError("(pinecall <verb> --help shows the verb's flags)")
    .hook("preAction", (root) => {
      // Read here, not at parse: the Context is handed to every domain before argv is known.
      const flags = root.opts();
      ctx.env = flags.prod === true ? "production" : "sandbox";
      ctx.io.json = flags.json === true;
    });
  for (const load of DOMAINS) (await load()).register(program, ctx);
  return program;
}
