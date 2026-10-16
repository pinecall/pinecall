/** `pinecall new | generate`: a new project, an agent in it, one more golden for an agent. */

import { relative, resolve } from "node:path";

import type { Command } from "@commander-js/extra-typings";

import type { Context } from "../context.js";
import * as render from "./render.js";
import * as service from "./service.js";

const NEW = `
Writes ./<name>/, the project: its toolchain (package.json, Gemfile or pyproject.toml), a README and
an empty agents/. A project is the business; its agents are the folders under agents/, each named
by its slug on the gateway. --agent writes the first one too: agents/<agent>/ holding the class — a
receptionist that takes a message — its ring-0 test and one golden. Names are lowercase letters,
digits and dashes, starting with a letter.

Examples
  $ pinecall new clinica-dental --agent sofia
  $ pinecall new clinica-dental --ruby && cd clinica-dental && pinecall generate agent sofia
`;

const GENERATE = `
Run at the project's root, the folder that holds agents/. It writes files and nothing else: no
key, no gateway, and never over a file that is there.

agent <name> is agents/<name>/: the class, its ring-0 test and one golden, in the project's
language. golden <name> is agents/<agent>/test/goldens/<name>.json: a turn for each caller's line
(--say, in order), and the tools the whole call must make (--tool, its expect). What must follow
each turn and the rest of expect are added by hand (docs.pinecall.io/concepts/golden-expectations).

Examples
  $ pinecall g golden asks-for-a-refund --say "Hi, I want a refund." --say "It's Ana Ruiz." --tool takeMessage
`;

export function register(program: Command, ctx: Context): void {
  program
    .command("new")
    .description("a new project, in TypeScript, Ruby or Python, and its first agent with --agent")
    .argument("<name>")
    .option("--agent <name>", "the first agent too, under agents/<name>/")
    .option("--typescript", "the class in TypeScript (agent.tsx, vitest); the default")
    .option("--ruby", "the class in Ruby (agent.rb, a view in ERB, minitest)")
    .option("--python", "the class in Python (agent.py, a view in Jinja, pytest, uv)")
    .addHelpText("after", NEW)
    .action((name, flags) => {
      const written = service.createProject(resolve(ctx.cwd, name), name, service.templateOf(flags) ?? "typescript", flags.agent);
      ctx.io.result(written, (one) => render.nextSteps(relative(ctx.cwd, one.root) || ".", one.template, one.agent));
    });

  const generate = program.command("generate").alias("g").description("an agent in this project, or one more golden for one of its agents").addHelpText("after", GENERATE);
  generate
    .command("agent")
    .argument("<name>")
    .option("--typescript")
    .option("--ruby")
    .option("--python")
    .action((name, flags) => ctx.io.result(service.createAgent(ctx.cwd, name, service.templateOf(flags)), render.wrote));
  generate
    .command("golden")
    .argument("<name>")
    .requiredOption("--say <line...>", "what the caller says, one line a turn, in order (required)")
    .option("--tool <name...>", "a tool the call must make")
    .option("--agent <name>")
    .action((name, flags) => {
      const file = service.createGolden(ctx.cwd, service.GoldenInput.parse({ name, says: flags.say, tools: flags.tool ?? [], agent: flags.agent }));
      ctx.io.result([relative(ctx.cwd, file)], render.wrote);
    });
}
