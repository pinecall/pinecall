/** The knowledge and memory doors: bases, files, contacts' facts, and their goldens. */

import { z } from "zod";

/** One question whose expected chunk was not among the k returned, and what came back instead. */
export const GoldenMissSchema = z.strictObject({
  asks: z.string(),
  expects: z.string(),
  found: z.array(z.string()),
});

/**
 * POST /v1/knowledge/{base}/eval, the answer: how the index did on its own golden. Both figures
 * are computed by code, with no model, so two runs of the same golden over the same base answer
 * the same numbers.
 */
export const KnowledgeScoreSchema = z.strictObject({
  base: z.string(),
  model: z.string(),
  questions: z.int(),
  k: z.int(),
  recall_at_k: z.number(),
  ndcg_at_10: z.number(),
  took_ms: z.number(),
  misses: z.array(GoldenMissSchema),
});

export type KnowledgeScore = z.infer<typeof KnowledgeScoreSchema>;

/**
 * PUT /v1/knowledge/{base}, the answer: which base, how many chunks it became, and how long that
 * took.
 */
export const KnowledgePushedSchema = z.strictObject({
  base: z.string(),
  chunks: z.int(),
  took_ms: z.number(),
});

/** One knowledge base as the list draws it: its name, its size, and when it was last pushed. */
export const KnowledgeBaseSchema = z.strictObject({
  base: z.string(),
  chunks: z.int(),
  model: z.string(),
  pushed_at: z.number(),
});

export type KnowledgeBase = z.infer<typeof KnowledgeBaseSchema>;

/** GET /v1/knowledge: every base this org has pushed. */
export const KnowledgeListSchema = z.strictObject({
  bases: z.array(KnowledgeBaseSchema),
});

export type KnowledgeList = z.infer<typeof KnowledgeListSchema>;

/**
 * One fact of a contact's history: a MemoryFact with the two dates that bound it. A fact is never
 * deleted, only superseded, so the history keeps every version.
 */
export const ContactFactSchema = z.strictObject({
  id: z.string().nullish(),
  text: z.string(),
  category: z.string().nullish(),
  source: z.string().nullish(),
  valid_from: z.number(),
  invalidated_at: z.number().nullable(),
});

export type ContactFact = z.infer<typeof ContactFactSchema>;

/**
 * GET /v1/contacts/{contact}/memory: everything memory ever kept about one contact, current facts
 * first.
 */
export const ContactMemorySchema = z.strictObject({
  facts: z.array(ContactFactSchema),
});

export type ContactMemory = z.infer<typeof ContactMemorySchema>;

/**
 * DELETE /v1/contacts/{contact}/memory, the answer: how many facts the right to be forgotten
 * erased.
 */
export const ForgottenSchema = z.strictObject({
  forgotten: z.int(),
});

export type Forgotten = z.infer<typeof ForgottenSchema>;

/**
 * One question memory did not answer whole: what it wanted and did not get, and what came back
 * instead. GoldenMiss is the knowledge base's and names the one chunk that should have won; a
 * memory question may expect several facts and miss some of them.
 */
export const MemoryMissSchema = z.strictObject({
  asks: z.string(),
  missing: z.array(z.string()),
  found: z.array(z.string()),
});

/**
 * POST /v1/contacts/memory/eval, the answer: how memory ranked the facts its own golden asked for.
 * Both figures are computed by code, with no model in the loop, so two runs of one golden answer
 * the same numbers.
 */
export const MemoryScoreSchema = z.strictObject({
  model: z.string(),
  questions: z.int(),
  k: z.int(),
  recall_at_k: z.number(),
  ndcg_at_10: z.number(),
  took_ms: z.number(),
  misses: z.array(MemoryMissSchema),
});

export type MemoryScore = z.infer<typeof MemoryScoreSchema>;

/**
 * One thing that did not hold about a case: which of the questions, and the evidence in a sentence
 * a person can act on.
 */
export const ExtractionBrokeSchema = z.strictObject({
  check: z.string(),
  detail: z.string(),
});

/** One case, run: what memory would have kept, what admission refused, and what did not hold. */
export const ExtractionJudgedSchema = z.strictObject({
  name: z.string(),
  held: z.boolean(),
  wrote: z.array(z.string()).nullish(),
  refused: z.array(z.string()).nullish(),
  broke: z.array(ExtractionBrokeSchema).nullish(),
});

/**
 * POST /v1/agents/{slug}/memory/extraction, the answer: which model answered, how many cases held,
 * and every one of them. A verb prints this and a pipeline exits on it.
 */
export const ExtractionRunSchema = z.strictObject({
  agent: z.string(),
  model: z.string(),
  cases: z.int(),
  held: z.int(),
  took_ms: z.number(),
  results: z.array(ExtractionJudgedSchema),
});

export type ExtractionRun = z.infer<typeof ExtractionRunSchema>;

/** One file of a base as the list draws it. */
export const KnowledgeFileRowSchema = z.strictObject({
  path: z.string(),
  chars: z.int(),
  chunks: z.int(),
  pushed_at: z.number(),
});

/**
 * GET /v1/knowledge/{base}: every file of the base, by path, with its size and what it became.
 * Never the text: one file is read at a time.
 */
export const KnowledgeFilesSchema = z.strictObject({
  base: z.string(),
  kept: z.boolean(),
  files: z.array(KnowledgeFileRowSchema),
});

export type KnowledgeFiles = z.infer<typeof KnowledgeFilesSchema>;

/** GET /v1/knowledge/{base}/files/{path}: one file, text and all. */
export const KnowledgeFileReadSchema = z.strictObject({
  path: z.string(),
  text: z.string(),
  chunks: z.int(),
  pushed_at: z.number(),
});

export type KnowledgeFileRead = z.infer<typeof KnowledgeFileReadSchema>;

/**
 * PUT /v1/knowledge/{base}/files/{path}, the answer: which file, how many chunks it became, and
 * how long that took.
 */
export const KnowledgeFilePushedSchema = z.strictObject({
  base: z.string(),
  path: z.string(),
  chunks: z.int(),
  took_ms: z.number(),
});

export type KnowledgeFilePushed = z.infer<typeof KnowledgeFilePushedSchema>;

/** One base and the agents whose settings attach it. */
export const KnowledgeUseSchema = z.strictObject({
  base: z.string(),
  agents: z.array(z.string()),
});

/**
 * GET /v1/knowledge/attached: which agents read each base, off every agent's newest settings in
 * this world.
 */
export const KnowledgeUsesSchema = z.strictObject({
  bases: z.array(KnowledgeUseSchema),
});
