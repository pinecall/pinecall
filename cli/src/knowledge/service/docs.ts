/** The documents an agent searches: a folder pushed as a base, the bases listed and dropped, a golden held against one, and who reads which. */

import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join, relative, resolve, sep } from "node:path";

import { z } from "zod";

import * as api from "../../api/knowledge.js";
import type { Context } from "../../context.js";
import { PinecallError, UsageError } from "../../errors.js";
import { isDirectory, type AgentHome } from "../../project/layout.js";
import { questionsOf } from "./cases.js";
import { cornerRead, readSettings, writeCorner } from "./settings.js";

/** The shape of one question of the retrieval golden, as the refusals name it. */
const DOCS_QUESTION = "{asks, expects}";

export const NO_DIRECTORY = (directory: string): string => `no documents directory at ${directory}`;
export const NO_MARKDOWN = (directory: string): string => `no *.md under ${directory}: nothing to push`;
export const NOT_ATTACHED = (agent: string, base: string): string => `${base} is not attached to ${agent}`;

/** What `docs push` takes: a folder and a base, or the agent whose `agents/<name>/docs/` and slug they default to. */
export const PushDocsInput = z.object({
  dir: z.string().min(1).optional(),
  base: z.string().min(1).optional(),
  agent: z.string().min(1).optional(),
  file: z.string().min(1).optional(),
});
export type PushDocsInput = z.infer<typeof PushDocsInput>;

/** What `docs eval` takes: a golden and a base, or the agent whose `goldens/docs.json` and slug they default to; `k` left out is the attachment's. */
export const EvalDocsInput = z.object({
  golden: z.string().min(1).optional(),
  base: z.string().min(1).optional(),
  k: z.number().int().min(1).optional(),
  agent: z.string().min(1).optional(),
  file: z.string().min(1).optional(),
});
export type EvalDocsInput = z.infer<typeof EvalDocsInput>;

/** What `docs attach` takes: the base, how a turn reads it, and whose corner it is written in. */
export const AttachBaseInput = z.object({
  base: z.string().min(1),
  k: z.number().int().min(1).optional(),
  mode: z.enum(["retrieved", "tool"]).optional(),
  minScore: z.number().min(0).optional(),
  agent: z.string().min(1).optional(),
  team: z.boolean().default(false),
});
export type AttachBaseInput = z.infer<typeof AttachBaseInput>;

/** What `docs detach` takes: the base, and whose corner it is taken out of. */
export const DetachBaseInput = z.object({
  base: z.string().min(1),
  agent: z.string().min(1).optional(),
  team: z.boolean().default(false),
});
export type DetachBaseInput = z.infer<typeof DetachBaseInput>;

/** One base pushed: what the gateway answered, plus how many files were sent and, in a project-wide push, whose. */
export interface DocsPushed extends api.KnowledgePushed {
  agent?: string;
  files: number;
}

/** An agent a project-wide `push` or `eval` passed over, and why. */
export interface DocsSkipped {
  agent: string;
  skipped: string;
}

/** An attachment written or taken out: which corner it landed in, at which version. */
export interface BaseAttached {
  agent: string;
  base: string;
  corner: string;
  version: number | null;
}

/**
 * Push a folder of Markdown as a base. With nothing named, at a project's root, every agent that
 * has a `agents/<name>/docs/` folder is pushed under its slug and the rest are named.
 */
export async function pushDocs(ctx: Context, input: PushDocsInput): Promise<(DocsPushed | DocsSkipped)[]> {
  const typed = input.dir !== undefined || input.base !== undefined;
  if (!typed) {
    const homes = ctx.agents({ file: input.file, agent: input.agent });
    if (homes.length > 1) {
      return Promise.all(
        homes.map((home) => (existsSync(home.docs) ? pushOne(ctx, home.docs, home.name, home.name) : { agent: home.name, skipped: `no documents at ${home.docs}` })),
      );
    }
    const home = homes[0]!;
    return [await pushOne(ctx, home.docs, home.name)];
  }
  const home = input.dir !== undefined && input.base !== undefined ? undefined : ctx.agent("docs push", { file: input.file, agent: input.agent });
  return [await pushOne(ctx, input.dir ?? home!.docs, input.base ?? home!.name)];
}

export async function listBases(ctx: Context): Promise<api.KnowledgeList> {
  return api.listBases(ctx.gateway());
}

export async function dropBase(ctx: Context, base: string): Promise<{ base: string }> {
  await api.deleteBase(ctx.gateway(), base);
  return { base };
}

/**
 * Score a golden against a base. With nothing named, at a project's root, every agent that has a
 * `goldens/docs.json` is scored against its slug's base and the rest are named.
 */
export async function evalDocs(ctx: Context, input: EvalDocsInput): Promise<(api.KnowledgeScore | DocsSkipped)[]> {
  const typed = input.golden !== undefined || input.base !== undefined;
  if (!typed) {
    const homes = ctx.agents({ file: input.file, agent: input.agent });
    if (homes.length > 1) {
      const scores: (api.KnowledgeScore | DocsSkipped)[] = [];
      for (const home of homes) {
        scores.push(existsSync(home.docsGolden) ? await evalOne(ctx, home.docsGolden, home.name, input.k, home) : { agent: home.name, skipped: `no golden at ${home.docsGolden}` });
      }
      return scores;
    }
    const home = homes[0]!;
    return [await evalOne(ctx, home.docsGolden, home.name, input.k, home)];
  }
  const home = input.golden !== undefined && input.base !== undefined ? undefined : ctx.agent("docs eval", { file: input.file, agent: input.agent });
  return [await evalOne(ctx, input.golden ?? home!.docsGolden, input.base ?? home!.name, input.k, home)];
}

/** Attach a base in a corner as a new settings version; an entry already there for it is replaced. */
export async function attachBase(ctx: Context, input: AttachBaseInput): Promise<BaseAttached> {
  const agent = ctx.slug("docs attach", { agent: input.agent });
  const docs: api.DocsConfig = { base: input.base };
  if (input.k !== undefined) docs.k = input.k;
  if (input.mode !== undefined) docs.mode = input.mode;
  if (input.minScore !== undefined) docs.min_score = input.minScore;
  const written = await writeCorner(
    ctx,
    agent,
    input.team,
    (config) => ({ ...config, bases: [...(config.bases ?? []).filter((one) => one.base !== input.base), docs] }),
    `attached ${input.base}`,
  );
  return { agent, base: input.base, corner: written.corner, version: written.version };
}

/** Detach a base in a corner as a new settings version; a base not attached there is a failed check. */
export async function detachBase(ctx: Context, input: DetachBaseInput): Promise<BaseAttached> {
  const agent = ctx.slug("docs detach", { agent: input.agent });
  const written = await writeCorner(
    ctx,
    agent,
    input.team,
    // Keep an empty list rather than dropping the field, or the corner falls back to the team's bases.
    (config) => ({ ...config, bases: (config.bases ?? []).filter((one) => one.base !== input.base) }),
    `detached ${input.base}`,
    (row) => {
      if (!(row?.config.bases ?? []).some((one) => one.base === input.base)) throw new PinecallError(NOT_ATTACHED(agent, input.base));
    },
  );
  return { agent, base: input.base, corner: written.corner, version: written.version };
}

export async function listAttached(ctx: Context): Promise<api.KnowledgeUses> {
  return api.listAttached(ctx.gateway());
}

/** Every *.md under a directory, recursively, with POSIX paths relative to it, sorted. */
export function markdownUnder(directory: string): api.KnowledgeFile[] {
  const found: api.KnowledgeFile[] = [];
  for (const entry of readdirSync(directory, { recursive: true, withFileTypes: true })) {
    if (!entry.isFile() || !entry.name.endsWith(".md")) continue;
    const path = join(entry.parentPath, entry.name);
    found.push({ path: relative(directory, path).split(sep).join("/"), text: readFileSync(path, "utf8") });
  }
  return found.sort((one, other) => (one.path < other.path ? -1 : 1));
}

/**
 * The k an agent reads a base with, off its attachment in the corner it reads; undefined when it
 * does not read the base, or the attachment named none. A golden asks what a turn gets: a base
 * attached with `--k 4` measured at the gateway's default of eight answers a question nobody's
 * calls are asking.
 */
export function kReadWith(answer: api.TuningAnswer | null, base: string): number | undefined {
  const corner = answer === null ? null : cornerRead(answer);
  return (corner?.config.bases ?? []).find((one) => one.base === base)?.k ?? undefined;
}

async function pushOne(ctx: Context, dir: string, base: string, agent?: string): Promise<DocsPushed> {
  const directory = resolve(dir);
  if (!isDirectory(directory)) throw new UsageError(NO_DIRECTORY(directory));
  const files = markdownUnder(directory);
  if (files.length === 0) throw new UsageError(NO_MARKDOWN(directory));
  const pushed = await api.pushBase(ctx.gateway(), base, files);
  return { ...(agent === undefined ? {} : { agent }), ...pushed, files: files.length };
}

// `home` is the agent whose attachment supplies k when none was typed; a golden and a base both
// named have no agent, and the gateway's default k answers.
async function evalOne(ctx: Context, golden: string, base: string, k: number | undefined, home: AgentHome | undefined): Promise<api.KnowledgeScore> {
  const questions = questionsOf(resolve(golden), DOCS_QUESTION);
  const attachment = k !== undefined || home === undefined ? null : await readSettings(ctx, home.name).catch(() => null);
  return api.scoreBase(ctx.gateway(), base, questions, k ?? kReadWith(attachment, base));
}
