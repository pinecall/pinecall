/** An agent's lexicon: how the voice says a word and what the ears must know, whole and versioned like the settings. */

import type { LexiconAnswer, LexiconBody, LexiconHistory } from "@pinecall/agents/wire";
import { z } from "zod";

import * as api from "../../api/agents.js";
import type { Context } from "../../context.js";
import { rowToStartFrom, versionGuarded } from "./corners.js";
import { agentNamed, WriteOptions } from "./settings.js";

export type { LexiconAnswer, LexiconHistory, LexiconRow } from "@pinecall/agents/wire";

/** Editable form of the lexicon: word → spoken form, plus the heard list. */
export interface Words {
  said: Record<string, string>;
  heard: string[];
}

/** What `lexicon add` takes: the word as written, and how the voice says it. */
export const SayWordInput = WriteOptions.extend({ word: z.string().min(1), say: z.string().min(1) });
export type SayWordInput = z.infer<typeof SayWordInput>;

/** What `lexicon hear` and `rm` take: the words. */
export const WordsInput = WriteOptions.extend({ words: z.array(z.string().min(1)).min(1) });
export type WordsInput = z.infer<typeof WordsInput>;

export async function showLexicon(ctx: Context, agent: string | undefined): Promise<LexiconAnswer> {
  return api.getLexicon(ctx.gateway(), agentNamed(ctx, agent));
}

export async function sayWord(ctx: Context, input: SayWordInput): Promise<LexiconAnswer> {
  return changed(ctx, input, (words) => ({ ...words, said: { ...words.said, [input.word]: input.say } }));
}

export async function hearWords(ctx: Context, input: WordsInput): Promise<LexiconAnswer> {
  return changed(ctx, input, (words) => ({ ...words, heard: [...new Set([...words.heard, ...input.words])] }));
}

export async function removeWords(ctx: Context, input: WordsInput): Promise<LexiconAnswer> {
  return changed(ctx, input, (words) => ({
    said: Object.fromEntries(Object.entries(words.said).filter(([word]) => !input.words.includes(word))),
    heard: words.heard.filter((word) => !input.words.includes(word)),
  }));
}

export async function lexiconHistory(ctx: Context, agent: string | undefined, team: boolean): Promise<LexiconHistory> {
  return api.getLexiconHistory(ctx.gateway(), agentNamed(ctx, agent), team);
}

// Read-modify-write of the whole row, guarded by the version it was read at: the words start from
// what this key reads; the guard is the version of the corner the gateway writes, or two saves at
// once overwrite each other, or a person's first one is refused.
async function changed(ctx: Context, options: WriteOptions, change: (words: Words) => Words): Promise<LexiconAnswer> {
  const name = agentNamed(ctx, options.agent);
  const gw = ctx.gateway();
  const standing = await api.getLexicon(gw, name);
  const row = rowToStartFrom(standing, options.team);
  return api.putLexicon(gw, name, {
    lexicon: bodyOf(change(wordsOf(row?.lexicon))),
    if_version: versionGuarded(standing, options.team, gw),
    note: options.note ?? null,
    team: options.team,
  });
}

function wordsOf(body: LexiconBody | undefined): Words {
  return { said: Object.fromEntries((body?.said ?? []).map((one) => [one.word, one.spoken])), heard: [...(body?.heard ?? [])] };
}

function bodyOf(words: Words): LexiconBody {
  return { said: Object.entries(words.said).map(([word, spoken]) => ({ word, spoken })), heard: words.heard };
}
