/** The project's voice app as its own framework describes it: asked of the serve entry, never loaded here. */

import { spawn } from "node:child_process";
import { basename, dirname } from "node:path";

import { UsageError } from "../errors.js";

import { languageOf, serveCommand } from "./language.js";
import { appFileOf } from "./layout.js";

/** What a project's voice app says of itself. */
export interface DescribedApp {
  name: string;
  /** Its page: the built folder from the project's root, the slug of the agent a visitor reaches, and the one environment it is served in when the app keeps it to one. */
  page: { dir: string; agent: string; only?: "sandbox" | "production" } | null;
}

/**
 * The page a release to `env` carries. An app may keep its page to one environment
 * (`app.page(dir, { only: "sandbox" })`, a guide beside the agent): a release to the other is the
 * app alone, with no page sent and none served.
 */
export function pageIn(said: DescribedApp["page"], env: "sandbox" | "production"): { dir: string; agent: string } | null {
  if (said === null || (said.only !== undefined && said.only !== env)) return null;
  return { dir: said.dir, agent: said.agent };
}

// A framework that has no `app` verb answers with its usage: such a project has no page to send.
const USAGE = /^usage:/;

/**
 * Ask the project's serve entry what its app is: `serve app --app <file> --file … --slug …`. The app
 * is the project's code, so it runs in the project's own process and framework. Null when the
 * framework the project pinned describes no app.
 */
export async function describedApp(root: string, app: string, agents: readonly string[], processEnv: NodeJS.ProcessEnv): Promise<DescribedApp | null> {
  const first = agents[0];
  if (first === undefined) return null;
  const args = ["--app", app, ...agents.flatMap((file) => ["--file", file, "--slug", basename(dirname(file))])];
  const [program, ...rest] = serveCommand(languageOf(first), "app", args, { root });
  const child = spawn(program!, rest, { stdio: ["ignore", "pipe", "pipe"], env: processEnv, cwd: root });
  let out = "";
  let err = "";
  child.stdout.on("data", (chunk: Buffer) => (out += chunk.toString()));
  child.stderr.on("data", (chunk: Buffer) => (err += chunk.toString()));
  const code = await new Promise<number>((exited) => child.on("close", (status) => exited(status ?? 1)));
  if (code !== 0 && USAGE.test(err.trim())) return null;
  if (code !== 0) throw new UsageError(err.trim() || `the project's app could not be read: its serve entry left with ${code}`);
  return JSON.parse(out.trim().split("\n").at(-1) ?? "null") as DescribedApp | null;
}

/**
 * The project's voice app as `start` hands it to the serve entry: the file at its root, when the project's own
 * framework has a word for a voice app. One from before voice apps has none and its serve entry refuses `--app`
 * as a flag nobody declared: such a project is served as it always was. A file there that is no voice app is
 * refused in the framework's own sentence, which names the way out.
 */
export async function servedApp(root: string, agents: readonly string[], processEnv: NodeJS.ProcessEnv): Promise<string | undefined> {
  const first = agents[0];
  const file = first === undefined ? undefined : appFileOf(root, languageOf(first));
  if (file === undefined) return undefined;
  return (await describedApp(root, file, agents, processEnv)) === null ? undefined : file;
}
