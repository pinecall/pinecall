/** A tenant's project on disk for one test: agents under `agents/`, the files a verb reads beside them, removed after the test. */

import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";

import { afterEach } from "vitest";

const made: string[] = [];

afterEach(() => {
  for (const folder of made.splice(0)) rmSync(folder, { recursive: true, force: true });
});

/** An empty folder of its own, gone after the test. */
export function folder(): string {
  const path = mkdtempSync(join(tmpdir(), "pinecall-cli-"));
  made.push(path);
  return path;
}

/** The smallest class the layout recognises: `agents/<name>/agent.ts`. Nothing runs it in these tests. */
export const AN_AGENT = 'import { Agent } from "@pinecall/agents";\n\nexport default class extends Agent {}\n';

/**
 * A project with these agents (TypeScript, one folder each) and these files, by path from the
 * root. Answers the root.
 */
export function project(agents: readonly string[] = ["front-desk"], files: Record<string, string> = {}): string {
  const root = folder();
  for (const name of agents) write(root, `agents/${name}/agent.ts`, AN_AGENT);
  for (const [path, text] of Object.entries(files)) write(root, path, text);
  return root;
}

/** Write one file under a root, its folders made. */
export function write(root: string, path: string, text: string): string {
  const file = join(root, path);
  mkdirSync(dirname(file), { recursive: true });
  writeFileSync(file, text);
  return file;
}
