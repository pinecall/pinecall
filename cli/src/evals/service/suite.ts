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

/** What one suite plays: the golden files or not, the models (a column each), the cases beside them, the settings version, the line. */
export const SuiteInput = SpokenInput.extend({
  files: z.boolean().default(true),
  models: z.array(z.string().min(1)).default([]),
  cases: z.array(z.string().min(1)).optional(),
  dataset: z.boolean().default(false),
  version: z.number().int().min(1, "a version of the agent's settings is a whole number from 1, as `pinecall agent history` lists them").optional(),
});
export type SuiteInput = z.infer<typeof SuiteInput>;

/** What `test` was asked to play: the three flags, and whether paths were named. */
export interface PlayAsked {
  files?: boolean | undefined;
  dataset?: boolean | undefined;
  cases?: string[] | undefined;
  paths?: boolean | undefined;
}

/**
 * What plays, from what was typed. Nothing typed plays the files and the approved dataset both;
 * `--files` the files alone, `--dataset` or `--case` the cases alone; paths named play beside
 * whatever cases were asked for.
 */
export function whatPlays(asked: PlayAsked): { files: boolean; dataset: boolean } {
  const cases = asked.cases !== undefined;
  return {
    files: asked.files === true || asked.paths === true || (!cases && asked.dataset !== true),
    dataset: asked.dataset === true || (!cases && asked.files !== true),
  };
}

/** A finished run as data: the run, each call's latency medians, the reproductions written for what broke, and which goldens were sent from disk. */
export interface SuiteReport {
  run: api.EvalRun;
  latencies: Latencies;
  reproductions: string[];
  held: boolean;
  /** The names sent as files; a golden of the matrix not among them is a case the gateway played. */
  files: string[];
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
  return { run, latencies, reproductions: writeReproductions(run, goldens, logs, under), held: held(run), files: goldens.map((one) => one.name) };
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

// The row is read again on each `run.changed` of the run, and every so often besides: a feed that
// dropped a frame never leaves a terminal waiting on a run that ended.
const LOOK_AGAIN_MS = 20_000;
// The gateway stops a run at fifteen minutes; a row still running past that is a gateway that
// died with it, and the terminal says so instead of waiting on.
const A_RUN_MAY_TAKE_MS = 16 * 60_000;

/** The run's row once it is no longer running: followed on the feed and read again on each change. */
export async function settledRun(ctx: Context, started: api.EvalRun, signal: AbortSignal, onChanged?: (run: api.EvalRun) => void): Promise<api.EvalRun> {
  if (started.status !== "running") return started;
  const stop = new AbortController();
  const stopped = (): void => stop.abort();
  signal.addEventListener("abort", stopped, { once: true });
  let settle: (run: api.EvalRun) => void = () => undefined;
  let broke: (why: unknown) => void = () => undefined;
  const settled = new Promise<api.EvalRun>((done, failed) => {
    settle = done;
    broke = failed;
  });
  let over = false;
  const look = async (): Promise<void> => {
    if (over) return;
    const run = await api.getRun(ctx.gateway(), started.id);
    if (over) return;
    onChanged?.(run);
    if (run.status !== "running") {
      over = true;
      settle(run);
    }
    else if (Date.now() - started.started_at * 1000 > A_RUN_MAY_TAKE_MS) throw new PinecallError(`${started.id} is still running past the gateway's deadline: the gateway that played it stopped — \`pinecall runs show ${started.id}\` reads what it judged`);
  };
  // One read at a time, in the order the feed spoke; a read that fails ends the wait with its reason.
  let reading = Promise.resolve();
  const ask = (): void => void (reading = reading.then(look).catch(broke));
  // Read once now: a run over before the feed opened is not waited on.
  ask();
  const every = setInterval(ask, LOOK_AGAIN_MS);
  const following = (async () => {
    for await (const entry of calls.followEntries(ctx.gateway(), { feed: true }, { types: ["run.changed"], onOpen: ask, signal: stop.signal })) {
      if ((entry.data as { run?: string })["run"] === started.id) ask();
    }
  })().catch(() => undefined);
  try {
    return await settled;
  } finally {
    clearInterval(every);
    signal.removeEventListener("abort", stopped);
    stop.abort();
    await following;
  }
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
 * Run a suite to its end: the gateway answers the run as it starts it, stored and `running`, and
 * plays it after; this side follows it on the org's feed (`run.changed`) until its row says it is
 * over, so a front can draw each golden as it lands. A 409 is the agent's run already going, told
 * by its id.
 */
export async function runSuite(ctx: Context, agent: string, goldens: Golden[], input: SuiteInput, app: string | undefined, listeners: SuiteListeners = {}): Promise<SuiteReport> {
  let started: api.EvalRun;
  try {
    started = await startSuite(ctx, agent, goldens, input, app);
  } catch (failed) {
    if (failed instanceof GatewayError && failed.status === 409) throw new PinecallError(await busyWith(ctx, agent, failed));
    throw failed;
  }
  listeners.onStarted?.(started.id);
  listeners.onChanged?.(started);
  const run = await settledRun(ctx, started, ctx.signal, listeners.onChanged);
  return reportOf(ctx, run, goldens);
}

/** One stored run. */
export async function getRun(ctx: Context, id: string): Promise<api.EvalRun> {
  return api.getRun(ctx.gateway(), id);
}
