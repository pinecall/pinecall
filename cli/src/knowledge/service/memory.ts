/** One contact's memory and the right to be forgotten, the agent's memory policy, and the recall golden. */

import { resolve } from "node:path";

import { z } from "zod";

import * as api from "../../api/knowledge.js";
import type { Context } from "../../context.js";
import { questionsOf } from "./cases.js";
import { readSettings, writeCorner } from "./settings.js";

/** The shape of one question of the recall golden, as the refusals name it. */
const MEMORY_QUESTION = "{holds, asks, expects}";

// An erasure is never done on nobody's word: `data erase` asks for --yes the same way.
export const SAY_YES = (contact: string): string =>
  `forgetting ${contact} cannot be undone, and nobody is at a terminal to say so: run it again with --yes`;

/** What `memory policy` takes: the agent, the two lists (neither reads the policy), whose corner, a note. */
export const PolicyInput = z.object({
  agent: z.string().min(1).optional(),
  remember: z.array(z.string()).optional(),
  forget: z.array(z.string()).optional(),
  team: z.boolean().default(false),
  note: z.string().optional(),
});
export type PolicyInput = z.infer<typeof PolicyInput>;

/** What `memory eval` takes: a golden, or the agent whose `goldens/memory.json` it defaults to; `k` left out is the gateway's. */
export const EvalMemoryInput = z.object({
  golden: z.string().min(1).optional(),
  k: z.number().int().min(1).optional(),
  agent: z.string().min(1).optional(),
  file: z.string().min(1).optional(),
});
export type EvalMemoryInput = z.infer<typeof EvalMemoryInput>;

/** Everything memory kept about one contact, current facts first. */
export interface ContactRemembered extends api.ContactMemory {
  contact: string;
}

/** An agent's memory policy as its three corners hold it. */
export interface Policy {
  agent: string;
  answer: api.TuningAnswer;
}

export async function showContact(ctx: Context, contact: string): Promise<ContactRemembered> {
  const remembered = await api.getContactMemory(ctx.gateway(), contact);
  return { contact, ...remembered };
}

/** Erase everything memory kept about a contact; the command asks the person first, this does not. */
export async function forgetContact(ctx: Context, contact: string): Promise<api.Forgotten> {
  return api.deleteContactMemory(ctx.gateway(), contact);
}

/** Read the policy of the three corners; with a list typed, write the policy whole as the corner's next version. */
export async function policy(ctx: Context, input: PolicyInput): Promise<Policy> {
  const agent = ctx.slug("memory policy", { agent: input.agent });
  if (input.remember === undefined && input.forget === undefined) return { agent, answer: await readSettings(ctx, agent) };
  const written = await writeCorner(
    ctx,
    agent,
    input.team,
    (config) => ({
      ...config,
      memory: { remember: input.remember ?? config.memory?.remember ?? [], forget: input.forget ?? config.memory?.forget ?? [] },
    }),
    input.note ?? "memory policy",
  );
  return { agent, answer: written.answer };
}

/** Every question of a recall golden asked of memory; no contact of the org's is read or written. */
export async function evalMemory(ctx: Context, input: EvalMemoryInput): Promise<api.MemoryScore> {
  const golden = input.golden ?? ctx.agent("memory eval", { file: input.file, agent: input.agent }).memoryGolden;
  const questions = questionsOf(resolve(golden), MEMORY_QUESTION);
  return api.scoreMemory(ctx.gateway(), questions, input.k);
}
