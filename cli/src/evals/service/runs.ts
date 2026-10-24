/** The runs the gateway kept: listed, one shown, two diffed, a real call promoted to a candidate, each judge's drift. */

import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";

import type { CallScore, SessionLine } from "@pinecall/agents/wire";
import { z } from "zod";

import * as calls from "../../api/calls.js";
import * as cases from "../../api/cases.js";
import * as api from "../../api/evals.js";
import type { Context } from "../../context.js";
import { UsageError } from "../../errors.js";
import type { Expect, Golden } from "./goldens.js";
import { mediansOf, allEntries, type Latencies } from "./suite.js";

/** Calls read per drift; 200 is the sessions endpoint's maximum. */
export const DRIFT_CALLS = 200;
/** Allowed drop in percentage points before failing; the sign is ignored. */
export const THRESHOLD = 10;
const NAMED = 3;

export const CONSENT_BANS_THE_TOOL = "consent broke, so the tool that ran unasked is in expect.not_tools: keep it only if this call must never call it at all — the order itself is the runtime's own policy over state and input";
export const GROUNDED_IS_ASKED = "grounded broke, so expect.grounded asks that every price, hour, date and name the agent states is in the call's evidence";
export const NOTHING_BROKE = "nothing broke: write what this call must keep doing";
export const BROKE_UNASKED = (judges: string[]): string => `${judges.join(", ")} broke this call and no golden field asks it again: write what the call must do instead in expect`;

/** What `runs promote` takes: the call, the candidate's name, where it is written (the agent's candidates), the seq to cut the call at. */
export const PromoteInput = z.object({
  call: z.string().min(1),
  name: z.string().min(1).optional(),
  out: z.string().min(1),
  fromSeq: z.number().int().min(0).default(0),
});
export type PromoteInput = z.infer<typeof PromoteInput>;

const DRIFT_LIMIT = { error: `--limit takes a whole number of calls from 1 to ${DRIFT_CALLS}` };

/** What `runs drift` takes; the windows in seconds, the baseline the time BEFORE the window. */
export const DriftInput = z.object({
  agent: z.string().min(1),
  window: z.number().positive(),
  baseline: z.number().positive(),
  threshold: z.number().min(0).default(THRESHOLD),
  limit: z.number(DRIFT_LIMIT).int(DRIFT_LIMIT).min(1, DRIFT_LIMIT).max(DRIFT_CALLS, DRIFT_LIMIT).default(DRIFT_CALLS),
});
export type DriftInput = z.infer<typeof DriftInput>;

/** A promoted call: the file, the candidate, and the review notes. */
export interface Promoted {
  path: string;
  candidate: Golden;
  notes: string[];
}

/** One judge's pass rate in one window. */
export interface Rate {
  held: number;
  settled: number;
  percent: number;
}

/** One judge's rate in both windows and the change, in points; null when either window has no verdicts. */
export interface JudgeDrift {
  judge: string;
  before: Rate | null;
  now: Rate | null;
  delta: number | null;
}

/** One failing verdict with its evidence seqs. */
export interface Broke {
  call: string;
  judge: string;
  seqs: number[];
  reason: string;
}

/** Drift: per-judge rows, unjudged counts, recent failures, and the most negative delta. */
export interface Drift {
  agent: string;
  window: number;
  baseline: number;
  threshold: number;
  judges: JudgeDrift[];
  notJudged: { now: number; before: number };
  broke: Broke[];
  worst: number | null;
}

/** A finished call and its score. */
interface Judged {
  call: string;
  score: CallScore | null;
}

/** The most runs one list asks for: the gateway's own ceiling. */
export const RUNS_MOST = 200;
const A_LIMIT = { error: `--limit takes a whole number from 1 to ${RUNS_MOST}` };
export const RunsLimit = z.number(A_LIMIT).int(A_LIMIT).min(1, A_LIMIT).max(RUNS_MOST, A_LIMIT);

export async function listRuns(ctx: Context, limit: number, agent?: string): Promise<api.EvalRun[]> {
  return api.listRuns(ctx.gateway(), limit, agent);
}

/** One run, with each call's latency medians read off its log. */
export async function showRun(ctx: Context, id: string): Promise<{ run: api.EvalRun; latencies: Latencies }> {
  const run = await api.getRun(ctx.gateway(), id);
  const latencies: Latencies = {};
  for (const opened of run.calls) latencies[opened.call] = mediansOf(await allEntries(ctx, opened.call));
  return { run, latencies };
}

/** The scores that moved between two runs; a score new in the later one is listed only if broken. */
export async function diffRuns(ctx: Context, before: string, after: string): Promise<{ before: string; after: string; moved: Moved[] }> {
  const gw = ctx.gateway();
  const [was, now] = await Promise.all([api.getRun(gw, before), api.getRun(gw, after)]);
  return { before, after, moved: movedBetween(was, now) };
}

/** One score that moved. */
export interface Moved {
  golden: string;
  metric: string;
  was: "held" | "broken" | "not measured";
  now: "held" | "broken" | "not measured";
  reason: string;
}

export function movedBetween(was: api.EvalRun, now: api.EvalRun): Moved[] {
  const moved: Moved[] = [];
  const cellIn = (run: api.EvalRun, model: string, golden: string): api.Cell | undefined => run.matrix?.runs.find((one) => one.model === model && one.golden === golden);
  const word = (passed: boolean): "held" | "broken" => (passed ? "held" : "broken");
  for (const cell of now.matrix?.runs ?? []) {
    const before = cellIn(was, cell.model, cell.golden);
    for (const score of cell.scores) {
      const older = before?.scores.find((one) => one.metric === score.metric);
      if (older === undefined) {
        if (!score.passed) moved.push({ golden: cell.golden, metric: score.metric, was: "not measured", now: "broken", reason: score.reason });
        continue;
      }
      if (older.passed !== score.passed) moved.push({ golden: cell.golden, metric: score.metric, was: word(older.passed), now: word(score.passed), reason: score.reason });
    }
  }
  // Scores the newer run no longer measures, so a removed golden does not look like a fix.
  for (const cell of was.matrix?.runs ?? []) {
    const after = cellIn(now, cell.model, cell.golden);
    for (const score of cell.scores) {
      if (after?.scores.some((one) => one.metric === score.metric) !== true) moved.push({ golden: cell.golden, metric: score.metric, was: word(score.passed), now: "not measured", reason: "" });
    }
  }
  return moved;
}

/** The golden the gateway derives from one real call, written as a candidate a person reviews before keeping. */
export async function promoteCall(ctx: Context, input: PromoteInput): Promise<Promoted> {
  const candidate = (await cases.getCallGolden(ctx.gateway(), input.call, { name: input.name, fromSeq: input.fromSeq })) as Golden;
  await mkdir(input.out, { recursive: true });
  const path = join(input.out, `${candidate.name}.json`);
  await writeFile(path, `${JSON.stringify(candidate, null, 2)}\n`, "utf8");
  const scored = (await calls.listCallEntries(ctx.gateway(), input.call, { types: ["call.score"] })).entries.find((entry) => entry.type === "call.score");
  const broke = ((scored?.data as unknown as CallScore | undefined)?.judges ?? []).filter((judgment) => judgment.verdict === "broken").map((judgment) => judgment.name);
  return { path, candidate, notes: notesOn(candidate.expect ?? {}, broke) };
}

/** Each judge's held-rate over the window against the baseline before it, counted from `call.score` verdicts. */
export async function driftOf(ctx: Context, input: DriftInput, now = Date.now() / 1000): Promise<Drift> {
  if (input.baseline <= input.window) throw new UsageError("the baseline has to be longer than the window: it is the time BEFORE it");
  const sessions = await calls.listSessions(ctx.gateway(), input.agent, input.limit);
  const judgedNow = await judgedIn(ctx, finishedBetween(sessions, now - input.window, now));
  const judgedBefore = await judgedIn(ctx, finishedBetween(sessions, now - input.baseline, now - input.window));
  const scoredNow = judgedNow.filter(wasJudged);
  const scoredBefore = judgedBefore.filter(wasJudged);
  const names = [...new Set([...scoredNow, ...scoredBefore].flatMap((one) => (one.score?.judges ?? []).map((judgment) => judgment.name)))].sort();
  const judges = names.map((judge): JudgeDrift => {
    const [held, was] = [rateOf(judge, scoredNow), rateOf(judge, scoredBefore)];
    return { judge, before: was, now: held, delta: held !== null && was !== null ? held.percent - was.percent : null };
  });
  const deltas = judges.map((row) => row.delta).filter((delta) => delta !== null);
  return {
    agent: input.agent,
    window: input.window,
    baseline: input.baseline,
    threshold: input.threshold,
    judges,
    notJudged: { now: judgedNow.length - scoredNow.length, before: judgedBefore.length - scoredBefore.length },
    broke: brokenIn(scoredNow),
    worst: deltas.length > 0 ? Math.min(...deltas) : null,
  };
}

/** Whether a judge fell further than the threshold allows. */
export function drifted(drift: Drift): boolean {
  return drift.worst !== null && drift.worst < -Math.abs(drift.threshold);
}

/** A window like `90m`, `24h` or `7d` in seconds; null if it is none. */
export function secondsOf(said: string): number | null {
  const written = /^(\d+)([smhd])$/.exec(said);
  if (written === null) return null;
  const sizes: Record<string, number> = { s: 1, m: 60, h: 3600, d: 86400 };
  return Number(written[1]) * (sizes[written[2] ?? "s"] ?? 1);
}

/** Finished calls that ended in `(from, to]`, newest first. */
function finishedBetween(sessions: SessionLine[], from: number, to: number): SessionLine[] {
  return sessions
    .filter((line) => !line.live && line.ended_at !== null && line.ended_at > from && line.ended_at <= to)
    .sort((one, other) => (other.ended_at ?? 0) - (one.ended_at ?? 0));
}

// Start just below the last seq so each call costs a one-entry page.
async function judgedIn(ctx: Context, sessions: SessionLine[]): Promise<Judged[]> {
  const judged: Judged[] = [];
  for (const line of sessions) {
    const page = await calls.listCallEntries(ctx.gateway(), line.call, { after: Math.max(0, line.last_seq - 1), types: ["call.score"], limit: 4 });
    const found = page.entries.filter((entry) => entry.type === "call.score").at(-1);
    judged.push({ call: line.call, score: found === undefined ? null : (found.data as unknown as CallScore) });
  }
  return judged;
}

// An absent `passed` means not judged, not failed; such calls are counted apart.
function wasJudged(judged: Judged): boolean {
  return judged.score !== null && judged.score.passed !== null && judged.score.passed !== undefined;
}

// Held over settled: `deferred` and `skipped` are left out, not counted as failures.
function rateOf(judge: string, judged: Judged[]): Rate | null {
  const verdicts = judged.flatMap((one) => one.score?.judges ?? []).filter((judgment) => judgment.name === judge).map((judgment) => judgment.verdict);
  const settled = verdicts.filter((verdict) => verdict === "held" || verdict === "broken").length;
  if (settled === 0) return null;
  const held = verdicts.filter((verdict) => verdict === "held").length;
  return { held, settled, percent: (held / settled) * 100 };
}

function brokenIn(judged: Judged[]): Broke[] {
  const broke: Broke[] = [];
  for (const one of judged) {
    const faults = (one.score?.judges ?? []).filter((judgment) => judgment.verdict === "broken");
    if (faults.length === 0) continue;
    for (const fault of faults) broke.push({ call: one.call, judge: fault.name, seqs: fault.evidence.seqs, reason: fault.reason });
    if (new Set(broke.map((named) => named.call)).size >= NAMED) break;
  }
  return broke;
}

// Review notes say what one field of the derived expect means; the file stays a valid golden. A judge
// that broke the call and has no field here (`expected-outcome` fits no golden) is named, or the note
// read as if the call held (T F11).
function notesOn(expect: Expect, broke: string[]): string[] {
  const notes: string[] = [];
  const named = new Set([...(expect.judges ?? []), ...(expect.not_tools !== undefined && expect.not_tools.length > 0 ? ["consent"] : []), ...(expect.grounded === true ? ["grounded"] : [])]);
  const unasked = broke.filter((judge) => !named.has(judge));
  if (expect.not_tools !== undefined && expect.not_tools.length > 0) notes.push(CONSENT_BANS_THE_TOOL);
  if (expect.grounded === true) notes.push(GROUNDED_IS_ASKED);
  if (expect.judges !== undefined && expect.judges.length > 0) notes.push(`these judges broke and are asked again by name: ${expect.judges.join(", ")}`);
  if (unasked.length > 0) notes.push(BROKE_UNASKED(unasked));
  if (notes.length === 0) notes.push(NOTHING_BROKE);
  return notes;
}
