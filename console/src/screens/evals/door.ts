/** Eval requests and schemas: runs, replay, promote, reproductions. */

import { z } from "zod";

import { post, read, type Credentials } from "@pinecall/core/api";
import { GoldenSchema } from "@pinecall/core/wire/rest-goldens";
import { dev } from "../../lib/dev";

// Screen-specific shapes, kept here rather than in the wire.
/** A golden run under one model, and the call it opened. */
const OpenedSchema = z.object({
  golden: z.string(),
  model: z.string(),
  call: z.string(),
});

/** One judge's result on one golden. `score` is LiveKit's value, shown as is, never averaged. */
const JudgedSchema = z.object({
  metric: z.string(),
  score: z.number(),
  passed: z.boolean(),
  reason: z.string(),
  criteria: z.string(),
  judge_calls: z.int(),
});
export type Judged = z.infer<typeof JudgedSchema>;

/** A (golden, model) cell: every judge's result and the call summary. */
const CellSchema = z.object({
  model: z.string(),
  golden: z.string(),
  scores: z.array(JudgedSchema),
  summary: z.record(z.string(), z.unknown()).nullable(),
});
export type Cell = z.infer<typeof CellSchema>;

/** The run's result matrix: models × goldens, judges, and cells. */
const MatrixSchema = z.object({
  models: z.array(z.string()),
  goldens: z.array(z.string()),
  metrics: z.array(z.string()),
  judge_calls: z.int(),
  runs: z.array(CellSchema),
  failures: z.array(z.object({ model: z.string(), golden: z.string(), metric: z.string() })),
});
export type Matrix = z.infer<typeof MatrixSchema>;

const EvalRunSchema = z.object({
  id: z.string(),
  agent: z.string(),
  started_at: z.number(),
  finished_at: z.number().nullable(),
  // `failed` means the run itself errored; a failing golden is a score, not a status.
  status: z.enum(["running", "done", "failed"]),
  calls: z.array(OpenedSchema),
  matrix: MatrixSchema.nullable(),
  error: z.string().nullable(),
});
export type EvalRun = z.infer<typeof EvalRunSchema>;

const EvalRunListSchema = z.object({ runs: z.array(EvalRunSchema) });

// Server-side maximum (runtime api/evals/runs.py); the agent filter is applied before the limit.
const AS_MANY_AS_IT_MAY = 200;

/** Every agent's runs in this world, newest first. */
export async function readEveryRun(credentials: Credentials): Promise<EvalRun[]> {
  return EvalRunListSchema.parse(await read(credentials, "/v1/evals/runs", { limit: AS_MANY_AS_IT_MAY })).runs;
}

/** One agent's runs, newest first. */
export async function readRuns(credentials: Credentials, agent: string): Promise<EvalRun[]> {
  const listed = EvalRunListSchema.parse(
    await read(credentials, "/v1/evals/runs", { agent, limit: AS_MANY_AS_IT_MAY }),
  );
  return listed.runs;
}

/**
 * Play cases of the org's dataset as a run, through the app holding the agent in this world, on a
 * version of its settings or the one standing; the gateway answers once every case is judged.
 */
export async function runCases(credentials: Credentials, agent: string, cases: string[], version: number | undefined): Promise<EvalRun> {
  return EvalRunSchema.parse(await post(credentials, "/v1/evals/run", { agent, cases, ...(version === undefined ? {} : { version }) }));
}

/** One ring-3 check result. */
const VerdictSchema = z.object({ check: z.string(), status: z.string(), detail: z.string() });

/** Ring-3 result: the call rebuilt from its log and checked by code, no model involved. */
const ReplayedSchema = z.object({
  call: z.string(),
  agent: z.string(),
  passed: z.boolean(),
  verdicts: z.array(VerdictSchema),
});
export type Replayed = z.infer<typeof ReplayedSchema>;

/** Run the runtime's code checks on a finished call without re-running it. */
export async function replayCall(credentials: Credentials, call: string): Promise<Replayed> {
  return ReplayedSchema.parse(await post(credentials, `/v1/evals/replay/${encodeURIComponent(call)}`, {}));
}

/** A golden candidate written from a call: file path, the golden as written, and notes for review. */
const PromotedSchema = z.object({
  path: z.string(),
  candidate: GoldenSchema.required({ turns: true }),
  notes: z.array(z.string()),
});
export type Promoted = z.infer<typeof PromotedSchema>;

/** Promote a call to the agent's `agents/<agent>/test/candidates` in the `pinecall start` directory. */
export async function promoteCall(credentials: Credentials, agent: string, call: string): Promise<Promoted> {
  return PromotedSchema.parse(await dev(credentials, agent, "promote.write", { call }));
}

/** Goldens of a run with reproduction files on this machine, and their folder. */
const WrittenSchema = z.object({ run: z.string(), folder: z.string(), goldens: z.array(z.string()) });
export type Written = z.infer<typeof WrittenSchema>;

/**
 * A failing golden's reproduction: verdicts and the verbatim model requests. The log stores only
 * prompt block hashes, so this file is the only copy of the text.
 */
const ReproductionSchema = z.object({
  run: z.string(),
  agent: z.string(),
  golden: z.string(),
  model: z.string(),
  call: z.string(),
  declared: z.unknown(),
  verdicts: z.array(z.object({ metric: z.string(), passed: z.boolean(), criteria: z.string(), reason: z.string() })),
  asked: z.unknown(),
});
export type Reproduction = z.infer<typeof ReproductionSchema>;

/** List reproductions for a run; a fully passing run has none. */
export async function readWritten(credentials: Credentials, agent: string, run: string): Promise<Written> {
  return WrittenSchema.parse(await dev(credentials, agent, "reproductions.roster", { run }));
}

/** Read one reproduction from the `pinecall start` process's disk. */
export async function readReproduction(credentials: Credentials, agent: string, run: string, golden: string): Promise<Reproduction> {
  return ReproductionSchema.parse(await dev(credentials, agent, "reproductions.read", { run, golden }));
}
