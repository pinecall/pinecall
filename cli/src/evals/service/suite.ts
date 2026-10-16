/** A golden suite run through the agent wherever it is held, scored by the gateway; its report, latencies and reproductions. */

import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import { z } from "zod";

import * as calls from "../../api/calls.js";
import type { Entry } from "../../api/calls.js";
import * as api from "../../api/evals.js";
import type { Context } from "../../context.js";
import { GatewayError, PinecallError, UsageError } from "../../errors.js";
import * as providers from "../../providers/service.js";
import type { Golden } from "./goldens.js";

/** Output directory of reproductions, relative to where the suite ran; one folder per run. */
export const REPRODUCTIONS = ".pinecall/evals";

/** The runner's model name for "whatever the agent declared"; reports show the declared model instead. */
export const DECLARED = "declared";

/** The column of the agent's own model: what its settings name, which this side never reads. */
export const DECLARED_AS = "the app's own model";

/** Placeholder for `asked` when requests were not recorded. */
export const NOT_RECORDED = "not recorded: this call's requests were built in the worker process, which a spoken run drives over LiveKit. The log below is the whole of what this call left behind.";

// Per-turn LiveKit metrics, in display order. Missing ones are omitted, never shown as zero.
export const TURN_METRICS = ["e2e_latency", "llm_node_ttft", "tts_node_ttfb"] as const;

/** Median turn metrics in seconds, as LiveKit measured them. */
export type Medians = Partial<Record<(typeof TURN_METRICS)[number], number>>;

/** Latency medians by call id. */
export type Latencies = Record<string, Medians>;

export const AMBIENCES = ["television", "cafe", "office", "street"] as const;

/** A spoken run's line: noise under the caller, what plays, and the share of packets lost. */
export const SpokenInput = z.object({
  voice: z.boolean().default(false),
  backgroundNoise: z.number().optional(),
  ambience: z.enum(AMBIENCES).optional(),
  packetLoss: z.number().min(0, "--packet-loss is a share of the packets: a number from 0 to 1, such as 0.05").max(1, "--packet-loss is a share of the packets: a number from 0 to 1, such as 0.05").optional(),
});
export type SpokenInput = z.infer<typeof SpokenInput>;

/** What one suite plays: the goldens, the models (a column each), the cases beside them, the settings version, the line. */
export const SuiteInput = SpokenInput.extend({
  models: z.array(z.string().min(1)).default([]),
  cases: z.array(z.string().min(1)).optional(),
  dataset: z.boolean().default(false),
  version: z.number().int().min(1, "a version of the agent's settings is a whole number from 1, as `pinecall agent history` lists them").optional(),
});
export type SuiteInput = z.infer<typeof SuiteInput>;

/** A finished run as data: the run, each call's latency medians, and the reproductions written for what broke. */
export interface SuiteReport {
  run: api.EvalRun;
  latencies: Latencies;
  reproductions: string[];
  held: boolean;
}

/** The ring 2 fields of a spoken run; a written one sends none of them, not even `voice: false`. */
export function spokenLineOf(input: SpokenInput): api.SpokenLine {
  if (!input.voice) return {};
  return {
    voice: true,
    ...(input.backgroundNoise === undefined ? {} : { interferer_db: input.backgroundNoise }),
    ...(input.ambience === undefined ? {} : { ambience: input.ambience }),
    ...(input.packetLoss === undefined ? {} : { packet_loss: input.packetLoss }),
  };
}

/** What the run plays beside the goldens: the cases named, the whole dataset, the settings version. */
export function playedOf(input: SuiteInput): api.Played {
  return {
    ...(input.cases === undefined ? {} : { cases: [...new Set(input.cases)] }),
    ...(input.dataset ? { dataset: true } : {}),
    ...(input.version === undefined ? {} : { version: input.version }),
  };
}

/** Whether a run plays any of the org's cases. */
export function playsCases(input: SuiteInput): boolean {
  return input.cases !== undefined || input.dataset;
}

/** The models named, each a column of the matrix; a name that means no model is refused. */
export function modelsOf(names: string[]): api.ModelConfig[] {
  return names.map((name) => {
    const model = providers.parseModel(name);
    if (model === undefined) throw new UsageError(providers.NOT_A_MODEL(name, "--model"));
    return model;
  });
}

/**
 * Start the suite on the gateway: it drives and scores the conversations against whoever holds the
 * agent in the env (the app named, when one is). The promise answers when every golden was judged.
 */
export async function startSuite(ctx: Context, agent: string, goldens: Golden[], input: SuiteInput, app?: string): Promise<api.EvalRun> {
  if (goldens.length === 0 && !playsCases(input)) throw new UsageError("no golden to play: name the goldens, or --case / --dataset");
  const models = modelsOf(input.models);
  return api.startRun(ctx.gateway(), {
    agent,
    goldens,
    ...playedOf(input),
    ...(models.length > 0 ? { models } : {}),
    ...(app === undefined ? {} : { app }),
    ...spokenLineOf(input),
  });
}

/** The sentence a 409 is told with: which run of this agent is going, and how to watch it. */
export async function busyWith(ctx: Context, agent: string, refused: GatewayError): Promise<string> {
  const newest = (await api.listRuns(ctx.gateway(), 1, agent))[0];
  if (newest?.status !== "running") return refused.message;
  return `a run is already going on ${agent} (${newest.id}) — pinecall runs show ${newest.id} to watch it`;
}

/** The id of the agent's run in flight: the runner admits one per agent, stored before the first call. */
export async function runInFlight(ctx: Context, agent: string): Promise<string | undefined> {
  const newest = (await api.listRuns(ctx.gateway(), 1, agent))[0];
  return newest?.status === "running" ? newest.id : undefined;
}

/** Whether every golden held. */
export function held(run: api.EvalRun): boolean {
  return run.status === "done" && (run.matrix?.failures.length ?? 0) === 0;
}

/** Read every call's log once, measure its turns, and write a reproduction for each golden that broke. */
export async function reportOf(ctx: Context, run: api.EvalRun, goldens: Golden[], under = REPRODUCTIONS): Promise<SuiteReport> {
  const logs: Record<string, Entry[]> = {};
  for (const opened of run.calls) logs[opened.call] = await allEntries(ctx, opened.call);
  const latencies: Latencies = {};
  for (const [call, entries] of Object.entries(logs)) latencies[call] = mediansOf(entries);
  return { run, latencies, reproductions: writeReproductions(run, goldens, logs, under), held: held(run) };
}

/** A whole call's log, page by page. */
export async function allEntries(ctx: Context, call: string): Promise<Entry[]> {
  const entries: Entry[] = [];
  let after = 0;
  for (;;) {
    const page = await calls.listCallEntries(ctx.gateway(), call, { after });
    entries.push(...page.entries);
    const last = page.entries.at(-1)?.seq;
    if (page.entries.length < calls.PAGE_MOST || last === undefined) return entries;
    after = last;
  }
}

/**
 * Median of each metric over a call's turns, read off each `turn.agent`'s metrics. Median, not mean,
 * so one cold first turn does not skew it; metrics never measured are omitted, not zeroed.
 */
export function mediansOf(entries: Entry[]): Medians {
  const medians: Medians = {};
  for (const name of TURN_METRICS) {
    const measured = entries
      .filter((entry) => entry.type === "turn.agent")
      .map((entry) => (entry.data["metrics"] as Record<string, unknown> | undefined)?.[name])
      .filter((value): value is number => typeof value === "number");
    if (measured.length > 0) medians[name] = median(measured);
  }
  return medians;
}

/**
 * One file per failing cell (golden, requests, call log, verdicts), the paths answered. The prompt
 * text appears only here: the log stores hashes of prompt blocks.
 */
export function writeReproductions(run: api.EvalRun, goldens: Golden[], logs: Record<string, Entry[]>, under: string): string[] {
  const broken = (run.matrix?.runs ?? []).filter((cell) => cell.scores.some((score) => !score.passed));
  if (broken.length === 0) return [];
  const folder = join(under, run.id);
  mkdirSync(folder, { recursive: true });
  // The model in the file name when several failed, or one overwrites the other.
  const several = new Set(broken.map((cell) => cell.model)).size > 1;
  return broken.map((cell) => {
    const call = run.calls.find((one) => one.golden === cell.golden && one.model === cell.model)?.call ?? "";
    const path = join(folder, `${several ? `${cell.golden} · ${cell.model.replace(/[/\\]/g, "-")}` : cell.golden}.json`);
    const reproduction = {
      run: run.id,
      agent: run.agent,
      golden: cell.golden,
      model: cell.model,
      call,
      declared: goldens.find((one) => one.name === cell.golden) ?? null,
      verdicts: cell.scores.map((score) => ({ metric: score.metric, passed: score.passed, criteria: score.criteria, reason: score.reason })),
      // Null (spoken runs) becomes a sentence, not `[]`, which would read as "no tools ran".
      asked: cell.asked ?? NOT_RECORDED,
      log: logs[call] ?? [],
    };
    writeFileSync(path, `${JSON.stringify(reproduction, null, 2)}\n`);
    return path;
  });
}

/** A run that ends on the gateway after this side stopped waiting (a long spoken suite): its row once it stops. */
export async function settledRun(ctx: Context, id: string, signal: AbortSignal): Promise<api.EvalRun> {
  for await (const entry of calls.followEntries(ctx.gateway(), { feed: true }, { types: ["run.changed"], signal })) {
    if ((entry.data as { run?: string })["run"] !== id) continue;
    const run = await api.getRun(ctx.gateway(), id);
    if (run.status !== "running") return run;
  }
  throw new PinecallError(`stopped waiting for ${id}: \`pinecall runs show ${id}\` reads it`);
}

function median(values: number[]): number {
  const sorted = [...values].sort((one, two) => one - two);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 1 ? sorted[middle]! : (sorted[middle - 1]! + sorted[middle]!) / 2;
}

/** What a suite tells whoever runs it while it goes: the run's id once stored, and its row each time it changes. */
export interface SuiteListeners {
  onStarted?: (id: string) => void;
  onChanged?: (run: api.EvalRun) => void;
}

/**
 * Run a suite to its end: started on the gateway, followed on the org's feed (`run.changed` of this
 * agent) so a front can draw it, answered as its report. A 409 is the agent's run already going, told
 * by its id. Node's fetch drops a response not started within five minutes, which a long spoken suite
 * passes: the run goes on on the gateway, and its row is read once it stops.
 */
export async function runSuite(ctx: Context, agent: string, goldens: Golden[], input: SuiteInput, app: string | undefined, listeners: SuiteListeners = {}): Promise<SuiteReport> {
  const stop = new AbortController();
  let id: string | undefined;
  const look = async (): Promise<void> => {
    id ??= await runInFlight(ctx, agent);
    if (id === undefined) return;
    listeners.onStarted?.(id);
    listeners.onChanged?.(await api.getRun(ctx.gateway(), id));
  };
  // One read at a time, in the order the feed spoke.
  let reading = Promise.resolve();
  const ask = (): void => void (reading = reading.then(look, look));
  const following = (async () => {
    for await (const entry of calls.followEntries(ctx.gateway(), { feed: true }, { types: ["run.changed"], onOpen: ask, signal: stop.signal })) {
      const change = entry.data as { run?: string; agent?: string };
      if (change.agent === agent && (id === undefined || change.run === id)) ask();
    }
  })().catch(() => undefined);
  let run: api.EvalRun;
  try {
    run = await startSuite(ctx, agent, goldens, input, app);
  } catch (failed) {
    if (failed instanceof GatewayError && failed.status === 409) throw new PinecallError(await busyWith(ctx, agent, failed));
    if (id === undefined || failed instanceof GatewayError) throw failed;
    run = await settledRun(ctx, id, ctx.signal);
  } finally {
    stop.abort();
    await reading.catch(() => undefined);
    await following;
  }
  return reportOf(ctx, run, goldens);
}

/** One stored run. */
export async function getRun(ctx: Context, id: string): Promise<api.EvalRun> {
  return api.getRun(ctx.gateway(), id);
}
