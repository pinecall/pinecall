// The folder a class declares as its base, pushed when the agent registers: `agents/<slug>/docs/`, every Markdown file under it.

import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";

import type { Agent } from "../agent/agent.js";
import type { Pinecall } from "../client/index.js";
import type { KnowledgeFile } from "../wire/agent-config.js";

/** Where an agent's documents are, beside its class. */
export const DOCS_FOLDER = "docs";

/** Every Markdown file under the folder, its path as the base keeps it (relative, `/` between parts); none for no folder. */
export function markdownUnder(folder: string): KnowledgeFile[] {
  if (!existsSync(folder) || !statSync(folder).isDirectory()) return [];
  const found: KnowledgeFile[] = [];
  const walk = (dir: string): void => {
    for (const name of readdirSync(dir).sort()) {
      const path = join(dir, name);
      if (statSync(path).isDirectory()) walk(path);
      else if (name.endsWith(".md")) found.push({ path: relative(folder, path).split("\\").join("/"), text: readFileSync(path, "utf8") });
    }
  };
  walk(folder);
  return found;
}

/**
 * A class that declares `docs` owns its base: the folder beside it is pushed once the agent
 * registers, the base's other files kept, so a start or a deploy needs no `pinecall docs push`.
 * Nothing is pushed for a class that declares no base, a folder that is not there, or one with no
 * Markdown in it. The line says what landed.
 */
export async function pushDeclaredDocs(pc: Pinecall, ctor: typeof Agent, file: string | undefined, report: ((line: string) => void) | undefined): Promise<void> {
  const base = ctor.docs?.base;
  if (base === undefined || file === undefined) return;
  const folder = join(dirname(resolve(file)), DOCS_FOLDER);
  const files = markdownUnder(folder);
  if (files.length === 0) return;
  const pushed = await pc.pushKnowledge(base, files);
  report?.(`${base}  ${files.length} file(s) pushed · ${pushed.chunks} chunk(s)${pushed.kept > 0 ? ` · ${pushed.kept} kept` : ""}`);
}
