/** `pinecall new | generate`: a new project, an agent in it, one more golden for an agent. */

import { relative, resolve } from "node:path";

import type { Command } from "@commander-js/extra-typings";

import * as accounts from "../accounts/service/index.js";
import type { Context } from "../context.js";
import { UsageError } from "../errors.js";
import { readLine } from "../kit/stdin.js";
import * as render from "./render.js";
import * as service from "./service.js";
import { repeated } from "../kit/flags.js";

const NEW = `
Writes ./<name>/, the project: its toolchain (package.json, Gemfile or pyproject.toml), a README and
an empty agents/. A project is the business; its agents are the folders under agents/, each named
by its slug on the gateway. --agent writes the first one too: agents/<agent>/ holding the class — a
receptionist that takes a message — its ring-0 test and one golden. Names are lowercase letters,
digits and dashes, starting with a letter.

On a machine signed in to a gateway (\`pinecall login\`, or a runtime \`pinecall-runtime setup\`
runs here), it writes pinecall.json too: that gateway and the org the project runs in — your only
one, or the one you pick when you belong to several (--org with nobody to ask). It holds no key:
commit it, and whoever clones the project runs it there, on their own sign-in.

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
    .option("--org <slug>", "the org it runs in, when you belong to several and nobody is at the terminal to be asked")
    .addHelpText("after", NEW)
    .action(async (name, flags) => {
      const template = service.templateOf(flags) ?? "typescript";
      // The org is chosen before anything is written: a refusal leaves no half-made project behind.
      const here = await service.orgsHere(ctx);
      if (here === undefined && flags.org !== undefined) throw new UsageError("--org names an org of a gateway, and this machine is signed in nowhere: `pinecall login [url]` first");
      const orgs = here !== undefined && "orgs" in here ? here.orgs : undefined;
      const org = orgs === undefined ? undefined : flags.org === undefined && orgs.length > 1 ? await askWhichOrg(ctx, orgs) : accounts.chooseOrg(orgs, flags.org);
      const written = service.createProject(resolve(ctx.cwd, name), name, template, flags.agent);
      if (here !== undefined && "unread" in here) ctx.io.warn(here.unread);
      const made = here === undefined || org === undefined ? written : await service.runIn(ctx, written, here.machine, org);
      ctx.io.result(made, (one) => render.nextSteps(relative(ctx.cwd, one.root) || ".", one));
    });

  const generate = program.command("generate").alias("g").description("an agent in this project, or one more golden for one of its agents").addHelpText("after", GENERATE);
  generate
    .command("agent")
    .description("one more agent in this project: its class, its test, one golden, its docs folder")
    .argument("<name>")
    .option("--typescript")
    .option("--ruby")
    .option("--python")
    .action((name, flags) => ctx.io.result(service.createAgent(ctx.cwd, name, service.templateOf(flags)), render.wrote));
  generate
    .command("golden")
    .description("a conversation the agent must hold, written as a file to fill in")
    .argument("<name>")
    .requiredOption("--say <line>", "what the caller says, one turn; again for the next, in order (required)", repeated)
    .option("--tool <name>", "a tool the call must make; again for another", repeated)
    .option("--agent <name>")
    .action((name, flags) => {
      const file = service.createGolden(ctx.cwd, service.GoldenInput.parse({ name, says: flags.say, tools: flags.tool ?? [], agent: flags.agent }));
      ctx.io.result([relative(ctx.cwd, file)], render.wrote);
    });
}

// A numbered list on the terminal; without a person at it, the slugs are named and the verb refuses.
async function askWhichOrg(ctx: Context, orgs: accounts.Org[]): Promise<accounts.Org> {
  if (!ctx.io.interactive) throw new UsageError(accounts.whichOrg(orgs));
  const slugs = orgs.map(accounts.slugOf);
  for (const line of render.orgChoices(slugs)) ctx.io.info(line);
  const answer = (await readLine("which org is this project? ", ctx.io)).trim();
  return accounts.chooseOrg(orgs, slugs[Number(answer) - 1] ?? answer);
}
