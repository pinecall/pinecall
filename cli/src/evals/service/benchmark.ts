/** An agent's benchmark from comparisons already played: every call read, the numbers made, and the report written as a folder anybody can open. */

import { cpSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { z } from "zod";

import { getVersion } from "../../api/accounts.js";
import * as calls from "../../api/calls.js";
import * as api from "../../api/evals.js";
import type { Context } from "../../context.js";
import { PinecallError, UsageError } from "../../errors.js";
import { clearsBoth, flagOf, heldUnderEvery, sayLine, underEach, type Condition, type Line } from "./conditions.js";
import { listPersonas } from "./personas.js";
import { byStanding, callersOf, callOf as counted, linesOf, movedSince, nameOf, notCountedOf, numberRounds, READ, recordingBegan, repliesOf, setupOf, unpricedOf, verdictOf, VERSION, type Bars, type BenchCall, type Benchmark, type Earlier, type Setup } from "@pinecall/agents/evals";

/** The page a report is read in: its markup, its style and its script, copied beside the report's data. */
export const PAGE_ROOT = fileURLToPath(new URL("../../../pages/benchmark/", import.meta.url));
const PAGE_FILES = ["index.html", "benchmark.css", "benchmark.js"] as const;
const READ_AS_A_BASELINE: readonly number[] = [1, VERSION];
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
  // Several conditions: each one's comparisons, the first being the baseline every other is read against. One or none is no condition.
  conditions: z.array(z.custom<Condition>()).default([]),
  // The conditions a setup must clear both bars under too, beside the baseline's, for the gate to pass.
  gateUnder: z.array(z.string().min(1)).default([]),
});
export type BenchmarkInput = z.infer<typeof BenchmarkInput>;

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

/** One row of a comparison as the report's call: its log read, its recording kept beside the page. */
async function callOf(ctx: Context, row: api.ComparisonRow & { comparison: string; condition?: string }, folder: string | null): Promise<BenchCall> {
  const entries = await logOf(ctx, row.call);
  const began = recordingBegan(entries, row.started_at);
  const audio = folder === null ? null : await calls.getRecording(ctx.gateway(), row.call);
  if (folder !== null && audio !== null) writeFileSync(join(folder, "calls", `${row.call}.ogg`), audio);
  return counted(row, {
    not_counted: notCountedOf(row, entries),
    replies_s: repliesOf(entries),
    unpriced: unpricedOf(entries),
    recording: audio === null ? null : `calls/${row.call}.ogg`,
    timed: began.said,
    lines: linesOf(entries, began.at),
  });
}

function commandOf(agent: string, spoken: boolean, callers: readonly string[], setups: readonly Setup[], conditions: readonly Condition[]): string {
  // Conditions played before do not say their lines: what makes this report again is the verb that read them.
  if (conditions.some((condition) => condition.line === null)) return ["pinecall benchmark", ...conditions.map((condition) => `--condition ${condition.name}:${condition.comparisons.join(",")}`)].join(" ");
  const repeats = Math.max(1, ...setups.flatMap((setup) => setup.rounds.map((round) => round.round)));
  const against = setups.filter((setup) => setup.kind !== "own settings").map((setup) => `--against ${Object.entries(setup.values).map(([knob, value]) => `${knob}=${String(value)}`).join(",")}`);
  return ["pinecall simulate", `--agent ${agent}`, ...(spoken ? ["--voice"] : []), ...callers.map((caller) => `--persona ${caller}`), ...against, ...(repeats > 1 ? [`--repeats ${String(repeats)}`] : []), ...conditions.map(flagOf), "--report"].join(" ");
}

/** An earlier report read from its file; refused when it is no report of this shape. */
function readBaseline(path: string): Benchmark {
  if (!existsSync(path)) throw new UsageError(`no file at ${path}: --baseline takes the report.json of an earlier benchmark`);
  const read = JSON.parse(readFileSync(path, "utf8")) as Partial<Benchmark> | null;
  // A report of several conditions is read by its baseline's line, which is what its setups' own numbers are.
  if (read === null || !READ_AS_A_BASELINE.includes(read.version ?? 0) || !Array.isArray(read.setups)) throw new UsageError(`${path} is not a report.json this version reads (version ${READ_AS_A_BASELINE.join(" or ")})`);
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
  // One condition is no condition: there is nothing to read it against.
  const conditions = input.conditions.length > 1 ? input.conditions : [];
  const ids = [...new Set(input.conditions.length > 0 ? input.conditions.flatMap((condition) => condition.comparisons) : input.comparisons)];
  const under = new Map<string, string>();
  for (const condition of conditions) for (const id of condition.comparisons) {
    if (under.has(id)) throw new UsageError(`${id} is named under ${under.get(id) ?? ""} and under ${condition.name}: a comparison was played on one line`);
    under.set(id, condition.name);
  }
  const unknown = input.gateUnder.find((name) => !conditions.some((condition) => condition.name === name));
  if (unknown !== undefined) throw new UsageError(conditions.length === 0 ? `--gate-under ${unknown} names a condition, and this benchmark has none: name them with --condition` : `--gate-under ${unknown}: the conditions are ${conditions.map((condition) => condition.name).join(", ")}`);
  const tables = await Promise.all(ids.map((id) => api.getComparison(gw, id)));
  const agent = tables[0]?.agent ?? "";
  const other = tables.find((table) => table.agent !== agent);
  if (other !== undefined) throw new UsageError(`${other.comparison} is ${other.agent}'s and ${tables[0]?.comparison ?? ""} is ${agent}'s: a benchmark is one agent's`);
  const earlier = input.baseline === undefined ? null : readBaseline(input.baseline);
  const folder = input.out === null ? null : resolve(input.out);
  if (folder !== null) mkdirSync(join(folder, "calls"), { recursive: true });

  const rows = new Map<string, api.ComparisonRow & { comparison: string; condition?: string }>();
  for (const table of tables) {
    const condition = under.get(table.comparison);
    for (const row of table.rows) if (!rows.has(row.call)) rows.set(row.call, { ...row, comparison: table.comparison, ...(condition === undefined ? {} : { condition }) });
  }
  const ended = [...rows.values()].filter((row) => row.ended_at !== null || row.why !== null);
  const all = await inTurns(ended, READ_AT_ONCE, (row) => callOf(ctx, row, folder));
  numberRounds(all);
  all.sort((one, other) => one.started_at - other.started_at);

  const bars: Bars = { floor: input.floor, ceiling_s: input.ceiling };
  const callers = callersOf(tables);
  const values = new Map<string, api.AgentValues>();
  for (const row of ended) if (!values.has(nameOf(row.against))) values.set(nameOf(row.against), row.against);
  // With conditions a setup's own numbers are the baseline's line, and each condition's are beside them.
  const setups = [...values].map(([name, one]): Setup => {
    const its = all.filter((call) => call.setup === name);
    if (conditions.length === 0) return setupOf(one, its, callers, bars);
    const each = underEach(one, its, conditions, callers, bars);
    return { ...each.baseline, under: each.under };
  });
  setups.sort(byStanding);
  if (earlier !== null) for (const setup of setups) {
    const was = earlier.setups.find((one) => one.name === setup.name) as Earlier | undefined;
    if (was !== undefined) setup.baseline = movedSince(setup, was);
  }
  const verdict = verdictOf(setups, bars);
  if (conditions.length > 0 && verdict.passed !== null) {
    const held = heldUnderEvery(setups, conditions);
    verdict.held_under_every = held.names;
    verdict.says = `${verdict.says}; ${held.says}`;
  }

  const written = await listPersonas(ctx, agent).catch(() => []);
  const spoken = tables.some((table) => table.voice);
  const report: Benchmark = {
    version: VERSION,
    made_at: new Date().toISOString(),
    agent,
    gateway: { url: gw.url, env: gw.env, version: await getVersion(gw) },
    comparisons: ids,
    conditions: conditions.map((condition) => {
      const its = all.filter((call) => call.condition === condition.name);
      return { name: condition.name, line: condition.line, says: sayLine(condition.line), comparisons: condition.comparisons, calls: its.length, counted: its.filter((call) => call.not_counted === null).length };
    }),
    spoken,
    command: commandOf(agent, spoken, callers, setups, conditions),
    bars,
    verdict,
    callers: callers.map((name) => {
      const one = written.find((persona) => persona.name === name);
      return { name, about: one?.about ?? "", goal: one?.goal ?? "", expects: one?.expects ?? [], behavior: one?.behavior ?? null };
    }),
    setups,
    refused: tables.flatMap((table) => (table.refused ?? []).map((one) => ({ caller: one.persona, setup: nameOf(one.against), why: one.why, ...(under.has(table.comparison) ? { condition: under.get(table.comparison) as string } : {}) }))),
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
export function requireCleared(made: Benchmarked, input: Pick<BenchmarkInput, "gate" | "gateUnder">): void {
  if (!input.gate && input.gateUnder.length === 0) return;
  const verdict = made.report.verdict;
  if (verdict.passed === null) throw new UsageError(verdict.says);
  if (!verdict.passed) throw new PinecallError(`the benchmark failed: ${verdict.says}`);
  const fell = made.report.setups.filter((setup) => setup.baseline?.regressed === true).map((setup) => setup.name);
  if (fell.length > 0) throw new PinecallError(`the benchmark fell against its baseline: ${fell.join("; ")} completed fewer calls than its earlier rounds moved among themselves`);
  // Held under a condition is the same setup clearing both bars there and on the baseline's line: two setups, each good on one, are no agent to ship.
  const holds = (setup: Setup): boolean => clearsBoth(setup) && input.gateUnder.every((name) => (setup.under ?? []).some((its) => its.condition === name && clearsBoth(its)));
  if (input.gateUnder.length > 0 && !made.report.setups.some(holds)) throw new PinecallError(`the benchmark failed under ${input.gateUnder.join(", ")}: no setup clears both bars there and on the baseline's line`);
}
