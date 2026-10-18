/** Scaffold: a new project and where it runs, an agent in it, one more golden for an agent. */

import { existsSync, mkdirSync, readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

import { z } from "zod";

import { listOrgs, slugOf, type Org } from "../accounts/service/index.js";
import type { Context } from "../context.js";
import { errorMessage, UsageError } from "../errors.js";
import { homeOf as pinecallHome } from "../kit/home.js";
import { writeProjectConfig, type ProjectConfig } from "../project/config.js";
import { prepareProjectKey } from "../project/credentials.js";
import { readSignIn, type MachineSignIn } from "../project/session.js";
import type { Golden } from "../evals/service/goldens.js";
import { agentFilesOf, homeOf, PROJECT_AGENTS, type AgentHome } from "../project/layout.js";
import { languageOf } from "../project/language.js";

/** The languages a project is written in, each a folder under templates/. */
export const TEMPLATES = ["typescript", "ruby", "python"] as const;
export type Template = (typeof TEMPLATES)[number];

/** A slug the gateway accepts: what the folder, the agent's name and its URL path all are; a project is named the same way. */
export const SLUG = /^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$/;

const TEMPLATE_ROOT = fileURLToPath(new URL("../../templates/", import.meta.url));
// npm drops a published `.gitignore`, so the template carries it under another name.
const RENAMED: Record<string, string> = { _gitignore: ".gitignore" };

/** What the project's first commands are, per language, and the file an agent's class is. */
export const NEXT: Record<Template, { install: string; ring0: string; language: string; file: string }> = {
  typescript: { install: "npm install", ring0: "npm test", language: "TypeScript", file: "agent.tsx" },
  ruby: { install: "bundle install", ring0: "bundle exec rake", language: "Ruby", file: "agent.rb" },
  python: { install: "uv sync", ring0: "uv run pytest", language: "Python", file: "agent.py" },
};

// A new TypeScript project depends on the framework this CLI is released with: every package is
// released at one version, so the framework of this CLI is ^ its own version.
const OURS = JSON.parse(readFileSync(new URL("../../package.json", import.meta.url), "utf8")) as { version: string };

export const NO_PROJECT_HERE = (cwd: string): string => `no project at ${cwd}: generate writes into the folder that holds ${PROJECT_AGENTS}/ — \`pinecall new <name>\` writes one`;

export const NO_AGENT_YET = "this project has no agent yet: `pinecall generate agent <name>`";

/** What `generate golden` takes: its name, the caller's lines in order, the tools the call must make, the agent. */
export const GoldenInput = z.object({
  name: z.string().regex(SLUG, "a golden's name is lowercase letters, digits and dashes, as its file is named"),
  says: z.array(z.string()).transform((lines) => lines.map((line) => line.trim()).filter((line) => line !== "")).pipe(z.array(z.string()).min(1, "a golden needs what the caller says: --say '…', once per line, in order")),
  tools: z.array(z.string()).default([]),
  agent: z.string().min(1).optional(),
});
export type GoldenInput = z.infer<typeof GoldenInput>;

/** A project written: where, in which language, its first agent when one was asked for, and where it runs. */
export interface Written {
  root: string;
  template: Template;
  agent?: string | undefined;
  /** What its pinecall.json names; unset when this machine was signed in nowhere. */
  runs?: ProjectConfig | undefined;
}

/** Where a new project could run: the gateway this machine signed in to last and the person's orgs there, or why they could not be read. */
export type OrgsHere = { machine: MachineSignIn; orgs: Org[] } | { machine: MachineSignIn; unread: string } | undefined;

/** The gateway this machine signed in to last, and the person's orgs there; undefined when it is signed in nowhere. */
export async function orgsHere(ctx: Context): Promise<OrgsHere> {
  const machine = readSignIn(pinecallHome(ctx.processEnv));
  if (machine === undefined) return undefined;
  try {
    return { machine, orgs: await listOrgs(ctx, machine) };
  } catch (failed) {
    return { machine, unread: `${machine.url} did not say your orgs (${errorMessage(failed)}): no pinecall.json was written, and the project runs in your sign-in's org until one is` };
  }
}

/** The project made to run in one org of the gateway: its pinecall.json written, and this machine's key there made now. */
export async function runIn(ctx: Context, written: Written, machine: MachineSignIn, org: Org): Promise<Written> {
  const runs: ProjectConfig = { gateway: machine.url, org: slugOf(org) };
  writeProjectConfig(written.root, runs);
  await prepareProjectKey(ctx.processEnv, written.root, pinecallHome(ctx.processEnv));
  return { ...written, runs };
}

/** The one language the flags name, or undefined when they name none; refused when they name more than one. */
export function templateOf(flags: Partial<Record<Template, boolean | undefined>>): Template | undefined {
  const named = TEMPLATES.filter((one) => flags[one] === true);
  if (named.length > 1) throw new UsageError(`${named.map((one) => `--${one}`).join(" or ")}, not both: one language`);
  return named[0];
}

/**
 * A new project at `root`: its toolchain and an empty `agents/`, and the first agent in it when one
 * is named. A project and an agent are two names: the business, and one of the agents that answer
 * for it. Refused for a name the gateway would not take, or a folder already in use.
 */
export function createProject(root: string, project: string, template: Template, agent?: string): Written {
  checkSlug(project, "a project's");
  if (agent !== undefined) checkSlug(agent);
  if (existsSync(root) && readdirSync(root).length > 0) throw new UsageError(`${root} already holds files: new writes into an empty folder`);
  const words = { ...wordsFor(project, template), project, ProjectTitle: titleOf(project) };
  for (const tree of [join(TEMPLATE_ROOT, "common"), join(TEMPLATE_ROOT, template, "project")]) copyTree(tree, root, words);
  mkdirSync(join(root, PROJECT_AGENTS), { recursive: true });
  if (agent !== undefined) createAgent(root, agent, template);
  return { root, template, agent };
}

/**
 * One agent in the project at `root`, in the language asked or else the project's: its folder under
 * agents/, holding its class, its ring-0 test and one golden. The files, relative to the root.
 */
export function createAgent(root: string, slug: string, language?: Template): string[] {
  if (!existsSync(join(root, PROJECT_AGENTS))) throw new UsageError(NO_PROJECT_HERE(root));
  checkSlug(slug);
  const template = language ?? projectLanguage(root);
  const there = join(root, PROJECT_AGENTS, slug);
  if (existsSync(there) && readdirSync(there).length > 0) throw new UsageError(`${relative(root, there)} already holds files: ${slug} is an agent of this project already`);
  return copyTree(join(TEMPLATE_ROOT, template, "agent"), there, wordsFor(slug, template)).map((file) => relative(root, file));
}

/** One golden of an agent: a turn for each of the caller's lines, and the tools that must be called; never written over. Its path. */
export function createGolden(root: string, input: GoldenInput): string {
  const home = agentOf(root, input.agent);
  const file = join(home.goldens, `${input.name}.json`);
  if (existsSync(file)) throw new UsageError(`${file} is there already: a golden is never written over`);
  const golden: Omit<Golden, "name"> = { turns: input.says.map((say) => ({ say })), expect: input.tools.length === 0 ? {} : { tools: [...input.tools] } };
  mkdirSync(home.goldens, { recursive: true });
  writeFileSync(file, `${JSON.stringify(golden, null, 2)}\n`);
  return file;
}

/** The words a template's `{{…}}` and `__slug__` stand for. */
export function wordsFor(slug: string, template: Template): Record<string, string> {
  const next = NEXT[template];
  return { slug, Class: titleOf(slug).replaceAll(" ", ""), Title: titleOf(slug), Language: next.language, install: next.install, ring0: next.ring0, file: next.file, agents: `^${OURS.version}` };
}

function titleOf(slug: string): string {
  return slug.split("-").map((part) => part[0]!.toUpperCase() + part.slice(1)).join(" ");
}

function checkSlug(slug: string, whose = "an agent's"): void {
  if (!SLUG.test(slug)) throw new UsageError(`${slug} cannot be ${whose} name: lowercase letters, digits and dashes, starting with a letter`);
}

// The project's agents are in one language as a rule (one `pinecall start` serves one); a project of none is TypeScript's.
function projectLanguage(root: string): Template {
  const languages = new Set(agentFilesOf(root).map(languageOf));
  if (languages.size > 1) throw new UsageError(`this project's agents are in ${[...languages].join(" and ")}: say which with --typescript, --ruby or --python`);
  return [...languages][0] ?? "typescript";
}

// The agent named, or the project's only one.
function agentOf(root: string, agent: string | undefined): AgentHome {
  const homes = agentFilesOf(root).map(homeOf);
  if (homes.length === 0) throw new UsageError(existsSync(join(root, PROJECT_AGENTS)) ? NO_AGENT_YET : NO_PROJECT_HERE(root));
  if (agent !== undefined) {
    const named = homes.find((one) => one.name === agent);
    if (named === undefined) throw new UsageError(`no agent ${agent} in this project: it has ${homes.map((one) => one.name).join(", ")}`);
    return named;
  }
  if (homes.length > 1) throw new UsageError(`this project has ${homes.length} agents: name one with ${homes.map((one) => `--agent ${one.name}`).join(" or ")}`);
  return homes[0]!;
}

// Every file written, so a caller can say what it wrote.
function copyTree(from: string, to: string, words: Record<string, string>): string[] {
  mkdirSync(to, { recursive: true });
  const written: string[] = [];
  for (const entry of readdirSync(from)) {
    const source = join(from, entry);
    const target = join(to, RENAMED[entry] ?? entry.replaceAll("__slug__", words["slug"]!));
    if (statSync(source).isDirectory()) written.push(...copyTree(source, target, words));
    else {
      writeFileSync(target, readFileSync(source, "utf8").replace(/\{\{(\w+)\}\}/g, (whole, word: string) => words[word] ?? whole));
      written.push(target);
    }
  }
  return written;
}
