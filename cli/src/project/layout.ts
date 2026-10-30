/** The tenant's project: one folder per agent under `agents/`, holding its class, its documents and its tests. */

import { existsSync, readdirSync, statSync } from "node:fs";
import { basename, dirname, join, resolve } from "node:path";

import { UsageError } from "../errors.js";
import { AGENT_FILES } from "./language.js";

/** Project folder holding one subfolder per agent. */
export const PROJECT_AGENTS = "agents";

/** An agent's own folders, inside `agents/<name>/`: its documents and its tests. */
export const AGENT_DOCS = "docs";
export const AGENT_TESTS = "test";

/** The project's folder of code two or more agents share: `start` reloads on a save there too. */
export const SHARED = "lib";

/** File names of the retrieval and recall goldens inside the goldens folder. */
export const DOCS_GOLDEN = "docs.json";
export const MEMORY_GOLDEN = "memory.json";

/**
 * One agent of the project and the paths a verb reads in its folder. Verbs never build these
 * paths themselves. Everything an agent is lives in its folder: copied, it is copied whole.
 *
 *     agents/<name>/agent.ts              the class and its private helpers
 *     agents/<name>/docs/                 what `docs push` sends when no folder is named
 *     agents/<name>/test/agent.test.ts    ring 0
 *     agents/<name>/test/goldens/         ring 1, plus the `docs.json` and `memory.json` goldens
 *     agents/<name>/test/memory/          extraction cases, one written call each
 *     agents/<name>/test/personas/        the agent's own simulated callers, one JSON file each, when the class declares them
 *     agents/<name>/judges/               the agent's own judges, one Markdown file each, when the class declares them
 *     agents/<name>/test/candidates/      real calls `runs promote` wrote, before a person keeps them
 *     lib/                                code shared by two or more agents
 */
export interface AgentHome {
  /** Absolute path of the class's file. */
  file: string;
  /** The agent's folder name under agents/, which is its slug. */
  name: string;
  /** Project root, where verbs run. */
  root: string;
  goldens: string;
  personas: string;
  judges: string;
  candidates: string;
  docs: string;
  docsGolden: string;
  memoryGolden: string;
  memoryCases: string;
}

/** The home of the class at `agents/<name>/agent.*`. */
export function homeOf(file: string): AgentHome {
  const path = resolve(file);
  const folder = dirname(path);
  const name = basename(folder);
  const root = dirname(dirname(folder));
  const tests = join(folder, AGENT_TESTS);
  return {
    file: path,
    name,
    root,
    goldens: join(tests, "goldens"),
    personas: join(tests, "personas"),
    judges: join(folder, "judges"),
    candidates: join(tests, "candidates"),
    docs: join(folder, AGENT_DOCS),
    docsGolden: join(tests, "goldens", DOCS_GOLDEN),
    memoryGolden: join(tests, "goldens", MEMORY_GOLDEN),
    memoryCases: join(tests, "memory"),
  };
}

/** Whether the path exists and is a directory. */
export function isDirectory(path: string): boolean {
  return existsSync(path) && statSync(path).isDirectory();
}

/** Agent files of the project at `root`, sorted; folders without an agent file are skipped. */
export function agentFilesOf(root: string): string[] {
  const folder = resolve(root, PROJECT_AGENTS);
  if (!existsSync(folder)) return [];
  return readdirSync(folder, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => AGENT_FILES.map((name) => resolve(folder, entry.name, name)).find((path) => existsSync(path)))
    .filter((path): path is string => path !== undefined)
    .sort();
}

// `--agent` takes a slug and `--file` a path; a path passed to `--agent` gets a pointer to `--file`.
const A_PATH = /\.(tsx?|rb|py)$|[/\\]/;

/** What a verb was told about which agent: `--file <path>`, `--agent <slug>`, or neither. */
export interface AgentChoice {
  file?: string | undefined;
  agent?: string | undefined;
}

/**
 * The agents a verb acts on: `file` if given, else every agent in the project, or the one
 * `agent` names by its folder's name.
 */
export function agentsOf(cwd: string, choice: AgentChoice = {}): AgentHome[] {
  if (choice.agent !== undefined && A_PATH.test(choice.agent)) {
    throw new UsageError(`--agent takes an agent's name (its folder under ${PROJECT_AGENTS}/); a file is --file ${choice.agent}`);
  }
  if (choice.file !== undefined) return [homeOf(choice.file)];
  const files = agentFilesOf(cwd);
  if (files.length === 0) throw new UsageError(noAgentHere(cwd));
  const homes = files.map(homeOf);
  if (choice.agent === undefined) return homes;
  const named = homes.find((home) => home.name === choice.agent);
  if (named !== undefined) return [named];
  throw new UsageError(`no agent ${choice.agent} in this project: it has ${homes.map((home) => home.name).join(", ")}`);
}

/** The single agent a conversational verb acts on; a project with several must name it. */
export function oneAgentOf(cwd: string, verb: string, choice: AgentChoice = {}): AgentHome {
  const homes = agentsOf(cwd, choice);
  if (homes.length > 1) {
    const names = homes.map((home) => `--agent ${home.name}`).join(" or ");
    throw new UsageError(`${verb} talks to one agent and this project has ${homes.length}: add ${names}`);
  }
  return homes[0]!;
}

/**
 * The slug a gateway verb acts on: `--file`'s folder, `--agent` as typed — the gateway knows the
 * agent, so no project is needed — else the project's one agent.
 */
export function slugOf(cwd: string, verb: string, choice: AgentChoice = {}): string {
  if (choice.file !== undefined) return homeOf(choice.file).name;
  if (choice.agent !== undefined) {
    if (A_PATH.test(choice.agent)) throw new UsageError(`--agent takes an agent's slug; a file is --file ${choice.agent}`);
    return choice.agent;
  }
  return oneAgentOf(cwd, verb).name;
}

function noAgentHere(cwd: string): string {
  return `no agent here: looked for ${PROJECT_AGENTS}/<name>/${AGENT_FILES.join(" or ")} in ${cwd}`;
}
