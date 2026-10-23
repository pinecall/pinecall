/** The folder as a checkout of the base: the base brought back into the folder, and one file taken out of the base. */

import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";

import { z } from "zod";

import * as api from "../../api/knowledge.js";
import type { Context } from "../../context.js";
import { PinecallError } from "../../errors.js";
import { markdownUnder, README } from "./docs.js";

/** What `docs pull` takes: a folder and a base, or the agent whose `agents/<name>/docs/` and slug they default to. */
export const PullDocsInput = z.object({
  dir: z.string().min(1).optional(),
  base: z.string().min(1).optional(),
  agent: z.string().min(1).optional(),
  file: z.string().min(1).optional(),
});
export type PullDocsInput = z.infer<typeof PullDocsInput>;

/** What `docs rm` takes: the file's path in the base, and the base or the agent whose slug it is. */
export const RemoveDocInput = z.object({
  path: z.string().min(1),
  base: z.string().min(1).optional(),
  agent: z.string().min(1).optional(),
});
export type RemoveDocInput = z.infer<typeof RemoveDocInput>;

/** One file of the folder after a pull: written from the base, unchanged, or the folder's own that the base has not (kept, never deleted). */
export interface PulledFile {
  /** The path in the base, as a push sends it. */
  path: string;
  /** Where it is on disk, absolute. */
  file: string;
  status: "written" | "unchanged" | "kept";
}

/** A base pulled: the folder it went into, whether the gateway keeps its files at all, and every file. */
export interface DocsPulled {
  base: string;
  dir: string;
  kept: boolean;
  files: PulledFile[];
}

/** One file taken out of a base. */
export interface DocRemoved {
  base: string;
  path: string;
}

/**
 * Bring the base into the folder: each of its files written where its path says, or left alone
 * when the text is the same; a file of the folder the base has not is named and kept. The folder's
 * README is the folder's, never the base's, and is not named.
 */
export async function pullDocs(ctx: Context, input: PullDocsInput): Promise<DocsPulled> {
  const home = input.dir !== undefined && input.base !== undefined ? undefined : ctx.agent("docs pull", { file: input.file, agent: input.agent });
  const dir = resolve(input.dir ?? home!.docs);
  const base = input.base ?? home!.name;
  const listed = await api.listFiles(ctx.gateway(), base);
  mkdirSync(dir, { recursive: true });
  const files: PulledFile[] = [];
  for (const row of listed.files) {
    const file = join(dir, row.path);
    // A path the gateway sends is written under the folder and nowhere else.
    if (relative(dir, file).startsWith("..")) throw new PinecallError(`${base} holds a file at ${row.path}, which is outside ${dir}: not written`);
    const read = await api.getFile(ctx.gateway(), base, row.path);
    if (existsSync(file) && readFileSync(file, "utf8") === read.text) {
      files.push({ path: row.path, file, status: "unchanged" });
      continue;
    }
    mkdirSync(dirname(file), { recursive: true });
    writeFileSync(file, read.text);
    files.push({ path: row.path, file, status: "written" });
  }
  const inBase = new Set(listed.files.map((row) => row.path));
  for (const local of markdownUnder(dir)) {
    if (!inBase.has(local.path) && local.path !== README) files.push({ path: local.path, file: join(dir, local.path), status: "kept" });
  }
  return { base, dir, kept: listed.kept, files };
}

/** Take one file out of the base; a path the base has not is the gateway's 404, said as it is. */
export async function removeDoc(ctx: Context, input: RemoveDocInput): Promise<DocRemoved> {
  const base = input.base ?? ctx.slug("docs rm", { agent: input.agent });
  await api.deleteFile(ctx.gateway(), base, input.path);
  return { base, path: input.path };
}
