/** The `project` tool: which project the tools act on, opening another, writing a new one, generating into it. */

import { existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";

import { z } from "zod";

import * as accounts from "../../accounts/service/index.js";
import * as service from "../../scaffold/service.js";
import { agentFilesOf, homeOf } from "../../project/layout.js";
import { languageOf } from "../../project/language.js";
import { homeOf as pinecallHome } from "../../kit/home.js";
import { readCredentials } from "../../project/credentials.js";
import { tool, ToolRefused, type ToolContext } from "../tool.js";
import { needed } from "./fields.js";

export const project = tool({
  name: "project",
  description: "The project the tools act on (`show`), another folder opened (`open`), a new project written (`new`), or an agent or a golden added to it (`generate`).",
  schema: {
    action: z.enum(["show", "open", "new", "generate"]).describe("show the project the tools act on; open another folder; new writes a project, and its first agent with `agent`; generate adds an agent or a golden to it"),
    path: z.string().optional().describe("`open`: the project's folder; `new`: the folder to write it in, beside the open project when left out"),
    name: z.string().optional().describe("`new`: the project's name; `generate`: the agent's or the golden's: lowercase letters, digits and dashes"),
    language: z.enum(service.TEMPLATES).optional().describe("`new` and `generate agent`: the agent's language; TypeScript for `new`, the project's for `generate`"),
    kind: z.enum(["agent", "golden"]).optional().describe("`generate`: one more agent, or one more golden of an agent"),
    say: z.array(z.string()).optional().describe("`generate golden`: what the caller says, one line a turn, in order"),
    tools: z.array(z.string()).optional().describe("`generate golden`: the tools that must be called"),
    agent: z.string().optional().describe("`new`: the first agent, under agents/<agent>/; `generate golden`: whose golden, the project's only agent when left out"),
    org: z.string().optional().describe("`new`: the org it runs in, when the person belongs to several; asked of the person, never guessed"),
  },
  manual:
    "`project show` says which folder every tool acts on: its agents, their language, and whether it has a key. The host's declared root, or the server's folder, is used when it holds `agents/`; `open` points at another, with nothing held. `new` writes a project — the business, named by `name` — and opens it, and its pinecall.json names the gateway this machine is signed in to and the org it runs in: the person's only one, or the `org` they name (with several and none named, `new` answers their slugs and writes nothing — ask the person); with `agent` it writes its first agent too, under `agents/<agent>/` (a receptionist that takes a message, its test and one golden); a TypeScript one runs at once on the framework this server lends it until `npm install` pins its own, a Ruby one after `bundle install`, a Python one after `uv sync`. `generate` adds to the open project, never over a file: `agent` an agent's folder under `agents/<name>/` (its class, its test, one golden), `golden` a conversation in `agents/<agent>/test/goldens/`: a turn for each of the caller's lines (`say`) and the tools the call must make (`tools`, its `expect`). What must follow each turn — its `then`: a tool with its arguments, a reply and its intent, the end — is added to the file by hand (docs.pinecall.io/concepts/golden-expectations); then `test run` holds the agent to it.",
  handler: async (args, ctx) => {
    if (args.action === "open") return shown(ctx, ctx.session.open(needed(args.path, "path")));
    if (args.action === "new") {
      const name = needed(args.name, "name");
      const parent = args.path === undefined ? (ctx.session.root === undefined ? process.cwd() : dirname(ctx.session.root)) : resolve(args.path);
      const language = args.language ?? "typescript";
      const here = await service.orgsHere(ctx);
      const orgs = here !== undefined && "orgs" in here ? here.orgs : undefined;
      if (orgs !== undefined && orgs.length > 1 && args.org === undefined) {
        return { written: false, orgs: orgs.map(accounts.slugOf), says: "Ask the person which org this project runs in, then call project new again with org." };
      }
      const org = orgs === undefined ? undefined : accounts.chooseOrg(orgs, args.org);
      const created = service.createProject(join(parent, name), name, language, args.agent);
      const written = here === undefined || org === undefined ? created : await service.runIn(ctx, created, here.machine, org);
      ctx.session.open(written.root);
      const first = written.agent === undefined ? "`project generate` with kind agent writes its first agent; then " : "";
      const next =
        language === "typescript"
          ? `${first}\`start\` runs it on the framework this server lends it; npm install in ${written.root} pins the project's own`
          : `${first}${language === "ruby" ? "bundle install" : "uv sync"} in ${written.root}, then \`start\``;
      const signIn = written.runs === undefined ? "; this machine is signed in nowhere: `login` first, and the project runs in the person's org" : "";
      return { ...shown(ctx, written.root), ...(written.runs === undefined ? {} : { runs: written.runs }), next: `${next}${signIn}`, ...(here !== undefined && "unread" in here ? { warning: here.unread } : {}) };
    }
    if (args.action === "generate") {
      const root = await ctx.session.project();
      const name = needed(args.name, "name");
      if (args.kind === "agent") return { written: service.createAgent(root, name, args.language), ...shown(ctx, root) };
      if (args.kind !== "golden") throw new ToolRefused("generate takes a kind: agent or golden");
      return { written: [service.createGolden(root, service.GoldenInput.parse({ name, says: args.say ?? [], tools: args.tools ?? [], agent: args.agent }))] };
    }
    return shown(ctx, await ctx.session.project());
  },
});

// The agents as every verb finds them: `agents/<name>/agent.(tsx|ts|rb|py)`, the folder's name their slug.
function shown(ctx: ToolContext, root: string): Record<string, unknown> {
  const credentials = readCredentials(ctx.processEnv, root, pinecallHome(ctx.processEnv));
  return {
    root,
    agents: agentFilesOf(root).map((file) => ({ name: homeOf(file).name, language: languageOf(file) })),
    key: credentials.key === undefined ? (credentials.missing ?? "none: call login") : `from ${credentials.source}`,
    ...(credentials.org === undefined ? {} : { org: credentials.org }),
    gateway: credentials.url,
    installed: [join("node_modules", "@pinecall", "agents"), "Gemfile.lock", ".venv"].some((made) => existsSync(join(root, made))),
  };
}
