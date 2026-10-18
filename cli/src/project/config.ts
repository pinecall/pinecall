/** `pinecall.json`: where a project runs — the gateway and the org — committed beside its agents, with no secret in it. */

import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";

import { z } from "zod";

import { UsageError } from "../errors.js";

/** The file at the project's root that names where it runs. */
export const PROJECT_FILE = "pinecall.json";

/** Where the project runs: one gateway, one org of it. */
export const ProjectConfig = z.strictObject({
  gateway: z.string().url(),
  org: z.string().min(1),
});
export type ProjectConfig = z.infer<typeof ProjectConfig>;

/** The project's file as read: what it names, and where it is. */
export interface FoundConfig {
  config: ProjectConfig;
  file: string;
}

/** The nearest `pinecall.json` walking up from a folder; undefined when no folder above has one. */
export function findProjectConfig(from: string): FoundConfig | undefined {
  for (let at = from; ; at = dirname(at)) {
    const file = join(at, PROJECT_FILE);
    if (existsSync(file)) return { config: parsed(file), file };
    if (dirname(at) === at) return undefined;
  }
}

/** Write the project's file at its root, the gateway without a trailing slash. */
export function writeProjectConfig(root: string, config: ProjectConfig): string {
  const file = join(root, PROJECT_FILE);
  const written: ProjectConfig = { gateway: config.gateway.replace(/\/$/, ""), org: config.org };
  writeFileSync(file, `${JSON.stringify(written, null, 2)}\n`);
  return file;
}

// A file that is there and wrong is said by name, never taken for no file at all.
function parsed(file: string): ProjectConfig {
  let read: unknown;
  try {
    read = JSON.parse(readFileSync(file, "utf8"));
  } catch {
    throw new UsageError(`${file} is not JSON: it names the project's gateway and org, {"gateway": "https://…", "org": "<slug>"}`);
  }
  const checked = ProjectConfig.safeParse(read);
  if (!checked.success) throw new UsageError(`${file} names the project's gateway and org, {"gateway": "https://…", "org": "<slug>"}: ${checked.error.issues.map((one) => one.message).join("; ")}`);
  return checked.data;
}
