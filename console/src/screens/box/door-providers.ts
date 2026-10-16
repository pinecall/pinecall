/** The providers row as the operator edits it: what a call runs on when nobody chose, read and written whole. */

import { z } from "zod";

import { put, read, type Credentials } from "@pinecall/core/api";

export const STAGES = ["stt", "llm", "tts"] as const;
export type StageName = (typeof STAGES)[number];

/** A vendor and, when not its plugin's own, a model; a default names who takes over, in order. */
export interface Stage {
  vendor: string;
  model?: string | null | undefined;
  fallbacks?: Stage[] | undefined;
}

const StageSchema: z.ZodType<Stage> = z.lazy(() =>
  z.looseObject({ vendor: z.string(), model: z.string().nullish(), fallbacks: z.array(StageSchema).optional() }),
);

/** What one model costs in US dollars, by the unit it is billed in; a unit left out is not billed. */
export const RATE_UNITS = ["input", "output", "cached_input", "cache_creation", "characters", "audio_seconds", "minutes"] as const;
export type RateUnit = (typeof RATE_UNITS)[number];
export type Rate = Partial<Record<RateUnit, number | null>> & { as_of?: string };

const RateSchema = z.looseObject({ as_of: z.string().optional() }).catchall(z.unknown());

// Everything the screen does not edit (models, listed voices, lines, tuning's own shape) rides
// along untouched: the row is written whole, so a key it never read is a key it would erase.
const RowSchema = z.looseObject({
  defaults: z.record(z.string(), StageSchema),
  voices: z.record(z.string(), z.string()).default({}),
  tuning: z.record(z.string(), z.unknown()).default({}),
  hints: z.array(z.string()).default([]),
  rates: z.record(z.string(), RateSchema).default({}),
  judge: z.looseObject({ llm: StageSchema, ceiling_usd: z.number() }).nullish(),
  caller: z.looseObject({ ceiling_usd: z.number(), llm: StageSchema.nullish() }).nullish(),
  embedding: z
    .looseObject({ vendor: z.string(), url: z.string(), model: z.string(), shape: z.string(), dimensions: z.number().optional() })
    .nullish(),
});

export interface ProvidersRow {
  defaults: Record<string, Stage>;
  voices: Record<string, string>;
  tuning: Record<string, unknown>;
  hints: string[];
  rates: Record<string, Rate>;
  judge?: { llm: Stage; ceiling_usd: number } | null;
  caller?: { ceiling_usd: number; llm?: Stage | null } | null;
  embedding?: { vendor: string; url: string; model: string; shape: string; dimensions?: number } | null;
  [kept: string]: unknown;
}

export async function readProvidersRow(credentials: Credentials): Promise<ProvidersRow> {
  return RowSchema.parse(await read(credentials, "/v1/ops/providers")) as ProvidersRow;
}

/** The row replaced whole; the gateway refuses a vendor not installed or not doing its stage. */
export async function saveProvidersRow(credentials: Credentials, row: ProvidersRow): Promise<ProvidersRow> {
  return RowSchema.parse(await put(credentials, "/v1/ops/providers", row)) as ProvidersRow;
}

/** A stage as one line: `anthropic/claude-haiku-5-5`, or the vendor alone for its plugin's own model. */
export function stageSaid(stage: Stage): string {
  return stage.model ? `${stage.vendor}/${stage.model}` : stage.vendor;
}

/** A line typed back into a stage: the first slash splits vendor from model (a model may hold more). */
export function stageOf(line: string): Stage | null {
  const typed = line.trim();
  if (typed === "") return null;
  const at = typed.indexOf("/");
  return at < 0 ? { vendor: typed } : { vendor: typed.slice(0, at), model: typed.slice(at + 1) };
}

/** Fallbacks typed as `vendor/model, vendor` into stages, in the order typed. */
export function fallbacksOf(typed: string): Stage[] {
  return typed.split(",").flatMap((line) => {
    const stage = stageOf(line);
    return stage === null ? [] : [stage];
  });
}
