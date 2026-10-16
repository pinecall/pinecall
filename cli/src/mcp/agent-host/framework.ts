/** A TypeScript project with nothing installed runs on the framework this server ships, lent to the agent's thread alone: nothing is written into the project. */

import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import { PinecallError } from "../../errors.js";
import { serveEntryOf } from "../../project/language.js";

const FRAMEWORK = "@pinecall/agents";

/**
 * What a thread is given to run a project that installed no framework: the server's serve entry,
 * a tsconfig that gives the project's files the framework's compiler flags (the project's own extends
 * a package it does not have), and the URL the thread's resolver asks from when the project cannot
 * answer `@pinecall/agents`. A link in the project's node_modules would be simpler, and npm would
 * adopt it into the lockfile a deploy installs from.
 */
export interface Lent {
  version: string;
  entry: string;
  tsconfig: string;
  /** A file inside the framework: `@pinecall/agents` resolved from here is the server's own. */
  from: string;
}

/** Whether the project installed its own framework, where every verb looks for it. */
export function installsItsOwn(root: string): boolean {
  try {
    serveEntryOf(root);
    return true;
  } catch {
    return false;
  }
}

/** The framework this server lends a project that has none; undefined for a project that installed its own. */
export function lentTo(root: string, ours: string = theServersFramework()): Lent | undefined {
  if (installsItsOwn(root)) return undefined;
  const manifest = join(ours, "package.json");
  return {
    version: (JSON.parse(readFileSync(manifest, "utf8")) as { version: string }).version,
    entry: createRequire(manifest).resolve(`${FRAMEWORK}/serve`),
    tsconfig: tsconfigFor(root, join(ours, "tsconfig.tenant.json")),
    from: pathToFileURL(manifest).href,
  };
}

// tsx gives a tsconfig's flags only to the files under its own folder, so the framework's cannot be named
// alone: one in the server's temp folder extends it and includes the project by its path.
function tsconfigFor(root: string, tenant: string): string {
  const folder = join(tmpdir(), "pinecall-mcp-lent", createHash("sha256").update(root).digest("hex").slice(0, 12));
  mkdirSync(folder, { recursive: true });
  const file = join(folder, "tsconfig.json");
  writeFileSync(file, `${JSON.stringify({ extends: tenant, include: [join(root, "**", "*")] }, null, 2)}\n`);
  return file;
}

/** What `start` and `status` say while the agent runs on a lent framework. */
export function lentLine(lent: Lent): string {
  return `${FRAMEWORK} ${lent.version} lent by this server: npm install in the project pins its own`;
}

/** The `@pinecall/agents` this CLI was installed with: the folder of its package.json. */
export function theServersFramework(): string {
  for (let folder = dirname(fileURLToPath(import.meta.resolve(`${FRAMEWORK}/client`))); ; folder = dirname(folder)) {
    const manifest = join(folder, "package.json");
    if (existsSync(manifest) && (JSON.parse(readFileSync(manifest, "utf8")) as { name?: string }).name === FRAMEWORK) return folder;
    if (dirname(folder) === folder) throw new PinecallError(`this server has no ${FRAMEWORK} of its own to lend`);
  }
}
