/** An agent's benchmark from comparisons already played: every call read, the numbers made, and the report written as a folder anybody can open. */

import { cpSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { z } from "zod";

import { getVersion } from "../../api/accounts.js";
import * as calls from "../../api/calls.js";
import type { Behavior } from "../../api/cases.js";
import * as api from "../../api/evals.js";
import type { Context } from "../../context.js";
import { PinecallError, UsageError } from "../../errors.js";
import { listPersonas } from "./personas.js";
import { movedSince, nameOf, setupOf, verdictOf, type Bars, type BenchCall, type Earlier, type Setup, type Verdict } from "./scorecard.js";
import { linesOf, notCountedOf, READ, recordingBegan, repliesOf, unpricedOf } from "./transcript.js";

/** The page a report is read in: its markup, its style and its script, copied beside the report's data. */
export const PAGE_ROOT = fileURLToPath(new URL("../../../pages/benchmark/", import.meta.url));
const PAGE_FILES = ["index.html", "benchmark.css", "benchmark.js"] as const;
/** The report's shape: a reader of `report.json` checks it, and a baseline of another is refused. */
export const VERSION = 1;
// A call's log and its recording are two reads; this many calls are read at once.
const READ_AT_ONCE = 6;
const A_SHARE = "--floor is the share of calls that must be completed: a number from 0 to 1, such as 0.9";
const SECONDS = "--ceiling is the middle reply allowed, in seconds: a number over 0, such as 1.5";

export const BenchmarkInput = z.object({
  comparisons: z.array(z.string().regex(/^cmp_[a-z0-9]+$/, "a comparison is named cmp_…: pinecall simulate prints it as it places the calls")).min(1),
  // The folder the report is written into; null writes none (a machine with no files) and reads no recording.
  out: z.string().min(1).nullable().default("benchmark"),
  floor: z.number().min(0, A_SHARE).max(1, A_SHARE).default(0.9),
  ceiling: z.number().positive(SECONDS).default(1.5),
  baseline: z.string().min(1).optional(),
  gate: z.boolean().default(false),
});
export type BenchmarkInput = z.infer<typeof BenchmarkInput>;

/** A simulated caller as the report presents it. */
export interface Caller {
  name: string;
  about: string;
  goal: string;
  expects: string[];
  behavior: Behavior | null;
}

/** `report.json`: every number of the page, and every call under them. */
export interface Benchmark {
  version: typeof VERSION;
  made_at: string;
  agent: string;
  gateway: { url: string; env: string; version: string | null };
  comparisons: string[];
  spoken: boolean;
  /** The command that places the same calls again. */
  command: string;
  bars: Bars;
  verdict: Verdict;
  callers: Caller[];
  /** Best first: the share completed, then the reply. */
  setups: Setup[];
  /** What the gateway never placed, in its words. */
  refused: { caller: string; setup: string; why: string }[];
  /** Calls still on the line when the report was made: in none of its numbers. */
  on_the_line: number;
  /** The earlier report the setups are held against, when one was given. */
  baseline: { made_at: string; comparisons: string[] } | null;
  calls: BenchCall[];
}

/** A report made: its numbers, and the folder it was written into when one was. */
export interface Benchmarked {
  report: Benchmark;
  folder: string | null;
}

async function inTurns<T, R>(items: readonly T[], atOnce: number, work: (item: T) => Promise<R>): Promise<R[]> {
  const done = new Array<R>(items.length);
  let next = 0;
  const taking = async (): Promise<void> => {
    for (let at = next++; at < items.length; at = next++) done[at] = await work(items[at] as T);
  };
  await Promise.all(Array.from({ length: Math.min(atOnce, items.length) }, taking));
  return done;
}

/** The part of a call's log a benchmark reads, page by page. */
async function logOf(ctx: Context, call: string): Promise<calls.Entry[]> {
  const entries: calls.Entry[] = [];
  let after = 0;
  for (;;) {
    const page = await calls.listCallEntries(ctx.gateway(), call, { after, types: READ });
    entries.push(...page.entries);
    if (page.next === null || page.next === after) return entries;
    after = page.next;
  }
}

function didIt(row: api.ComparisonRow): boolean | null {
  if (row.goal !== undefined && row.goal !== null) return row.goal === "held";
  return row.score === null ? null : row.score.passed;
}

/** One row of a comparison as the report's call: its log read, its recording kept beside the page. */
async function callOf(ctx: Context, row: api.ComparisonRow & { comparison: string }, folder: string | null): Promise<BenchCall> {
  const entries = await logOf(ctx, row.call);
  const began = recordingBegan(entries, row.started_at);
  const audio = folder === null ? null : await calls.getRecording(ctx.gateway(), row.call);
  if (folder !== null && audio !== null) writeFileSync(join(folder, "calls", `${row.call}.ogg`), audio);
  const goal = row.judges?.find((judge) => judge.name === "expected-outcome");
  return {
    call: row.call,
    comparison: row.comparison,
    caller: row.persona,
    setup: nameOf(row.against),
    round: 0,
    not_counted: notCountedOf(row, entries),
    completed: didIt(row),
    reason: goal?.reason ?? row.score?.reason ?? null,
    ended: row.end_reason,
    started_at: row.started_at,
    length_s: row.ended_at === null ? null : row.ended_at - row.started_at,
    reply_s: row.latency.e2e_latency,
    replies_s: repliesOf(entries),
    slowest_reply_s: row.slowest_reply ?? null,
    cost_usd: row.cost_usd,
    unpriced: unpricedOf(entries),
    stages: { llm_ttft: row.latency.llm_node_ttft, tts_ttfb: row.latency.tts_node_ttfb, transcription_delay: row.latency.transcription_delay, end_of_turn_delay: row.latency.end_of_turn_delay ?? null },
    judges: row.judges ?? [],
    hearing: row.hearing ?? null,
    recording: audio === null ? null : `calls/${row.call}.ogg`,
    timed: began.said,
    lines: linesOf(entries, began.at),
  };
}

// Several comparisons are one table: rounds placed apart. A caller's calls under a setup are numbered
// in the order they started, whichever comparison placed them, and a call that does not count takes
// no round: the one placed in its stead does.
function numberRounds(all: BenchCall[]): void {
  const seen = new Map<string, number>();
  for (const call of [...all].sort((one, other) => one.started_at - other.started_at)) {
    if (call.not_counted !== null) continue;
    const pair = `${call.setup}\n${call.caller}`;
    call.round = (seen.get(pair) ?? 0) + 1;
    seen.set(pair, call.round);
  }
}

function commandOf(agent: string, spoken: boolean, callers: readonly string[], setups: readonly Setup[]): string {
  const repeats = Math.max(1, ...setups.flatMap((setup) => setup.rounds.map((round) => round.round)));
  const against = setups.filter((setup) => setup.kind !== "own settings").map((setup) => `--against ${Object.entries(setup.values).map(([knob, value]) => `${knob}=${String(value)}`).join(",")}`);
  return ["pinecall simulate", `--agent ${agent}`, ...(spoken ? ["--voice"] : []), ...callers.map((caller) => `--persona ${caller}`), ...against, ...(repeats > 1 ? [`--repeats ${String(repeats)}`] : []), "--report"].join(" ");
}

/** An earlier report read from its file; refused when it is no report of this shape. */
function readBaseline(path: string): Benchmark {
  if (!existsSync(path)) throw new UsageError(`no file at ${path}: --baseline takes the report.json of an earlier benchmark`);
  const read = JSON.parse(readFileSync(path, "utf8")) as Partial<Benchmark> | null;
  if (read === null || read.version !== VERSION || !Array.isArray(read.setups)) throw new UsageError(`${path} is not a report.json this version reads (version ${String(VERSION)})`);
  return read as Benchmark;
}

function writeFolder(folder: string, report: Benchmark): void {
  for (const file of PAGE_FILES) cpSync(join(PAGE_ROOT, file), join(folder, file));
  const json = JSON.stringify(report, null, 1);
  writeFileSync(join(folder, "report.json"), `${json}\n`);
  // A page opened from the disk may not read a file beside it: the same report, as a script it loads.
  writeFileSync(join(folder, "report.data.js"), `window.PINECALL_BENCHMARK = ${JSON.stringify(report).replace(/</g, "\\u003c")};\n`);
}

/**
 * The benchmark of the comparisons named: every ended call read with its log and its recording, each setup's numbers,
 * the verdict against the two bars, and the folder written when one is asked for.
 */
export async function benchmark(ctx: Context, input: BenchmarkInput): Promise<Benchmarked> {
  const gw = ctx.gateway();
  const ids = [...new Set(input.comparisons)];
  const tables = await Promise.all(ids.map((id) => api.getComparison(gw, id)));
  const agent = tables[0]?.agent ?? "";
  const other = tables.find((table) => table.agent !== agent);
  if (other !== undefined) throw new UsageError(`${other.comparison} is ${other.agent}'s and ${tables[0]?.comparison ?? ""} is ${agent}'s: a benchmark is one agent's`);
  const earlier = input.baseline === undefined ? null : readBaseline(input.baseline);
  const folder = input.out === null ? null : resolve(input.out);
  if (folder !== null) mkdirSync(join(folder, "calls"), { recursive: true });

  const rows = new Map<string, api.ComparisonRow & { comparison: string }>();
  for (const table of tables) for (const row of table.rows) if (!rows.has(row.call)) rows.set(row.call, { ...row, comparison: table.comparison });
  const ended = [...rows.values()].filter((row) => row.ended_at !== null || row.why !== null);
  const all = await inTurns(ended, READ_AT_ONCE, (row) => callOf(ctx, row, folder));
  numberRounds(all);
  all.sort((one, other) => one.started_at - other.started_at);

  const bars: Bars = { floor: input.floor, ceiling_s: input.ceiling };
  const callers = [...new Set(tables.flatMap((table) => (table.personas.length > 0 ? table.personas : [table.persona])))];
  const values = new Map<string, api.AgentValues>();
  for (const row of ended) if (!values.has(nameOf(row.against))) values.set(nameOf(row.against), row.against);
  const setups = [...values].map(([name, one]) => setupOf(one, all.filter((call) => call.setup === name), callers, bars));
  setups.sort((one, other) => (other.completed.share ?? -1) - (one.completed.share ?? -1) || (one.reply.p50 ?? Infinity) - (other.reply.p50 ?? Infinity));
  if (earlier !== null) for (const setup of setups) {
    const was = earlier.setups.find((one) => one.name === setup.name) as Earlier | undefined;
    if (was !== undefined) setup.baseline = movedSince(setup, was);
  }

  const written = await listPersonas(ctx, agent).catch(() => []);
  const spoken = tables.some((table) => table.voice);
  const report: Benchmark = {
    version: VERSION,
    made_at: new Date().toISOString(),
    agent,
    gateway: { url: gw.url, env: gw.env, version: await getVersion(gw) },
    comparisons: ids,
    spoken,
    command: commandOf(agent, spoken, callers, setups),
    bars,
    verdict: verdictOf(setups, bars),
    callers: callers.map((name) => {
      const one = written.find((persona) => persona.name === name);
      return { name, about: one?.about ?? "", goal: one?.goal ?? "", expects: one?.expects ?? [], behavior: one?.behavior ?? null };
    }),
    setups,
    refused: tables.flatMap((table) => (table.refused ?? []).map((one) => ({ caller: one.persona, setup: nameOf(one.against), why: one.why }))),
    on_the_line: rows.size - ended.length,
    baseline: earlier === null ? null : { made_at: earlier.made_at, comparisons: earlier.comparisons },
    calls: all,
  };
  if (folder !== null) writeFolder(folder, report);
  return { report, folder };
}

// A gate is asked for by name: a report made to be read fails nobody's build. Asked for, a benchmark
// nobody judged is refused as a usage error, since "nobody looked" must never read as a pass.
/** With `--gate`: refuse a benchmark in which no setup clears both bars, or one that fell against its baseline. */
export function requireCleared(made: Benchmarked, input: Pick<BenchmarkInput, "gate">): void {
  if (!input.gate) return;
  const verdict = made.report.verdict;
  if (verdict.passed === null) throw new UsageError(verdict.says);
  if (!verdict.passed) throw new PinecallError(`the benchmark failed: ${verdict.says}`);
  const fell = made.report.setups.filter((setup) => setup.baseline?.regressed === true).map((setup) => setup.name);
  if (fell.length > 0) throw new PinecallError(`the benchmark fell against its baseline: ${fell.join("; ")} completed fewer calls than its earlier rounds moved among themselves`);
}
