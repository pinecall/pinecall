/** `pinecall benchmark`: the report of comparisons already played, and the same asked of a simulation as it ends with `--report`. */

import type { Command } from "@commander-js/extra-typings";

import type * as api from "../../api/evals.js";
import type { Context } from "../../context.js";
import { UsageError } from "../../errors.js";
import { numberOf, repeated } from "../../kit/flags.js";
import { HELP } from "../help.js";
import * as render from "../render/index.js";
import * as service from "../service/index.js";
import { placeComparison } from "./terminal.js";

/** The folder a report is written into when none is named. */
export const A_FOLDER = "benchmark";

/** What the report's own flags say, on either verb. */
export interface ReportFlags {
  floor?: string | undefined;
  ceiling?: string | undefined;
  baseline?: string | undefined;
  gate?: true | undefined;
  gateUnder?: string[] | undefined;
  countedOnly?: true | undefined;
  price?: string[] | undefined;
}

/** The report's flags, said once for both verbs. */
export const REPORT_FLAGS: readonly (readonly [string, string])[] = [
  ["--floor <share>", "the share of counted calls a setup must complete, 0 to 1 (0.9)"],
  ["--ceiling <seconds>", "the middle reply a setup may take, in seconds (1.5)"],
  ["--baseline <report.json>", "an earlier report: each setup is held against its own row there"],
  ["--gate", "exit 1 when no setup clears both bars, or one fell against the baseline"],
  ["--counted-only", "a report to publish: the calls that did not count are left out, listed nowhere and their recordings not kept"],
];
/** A price for a model the gateway priced nothing for, said again for each. */
export const PRICE = ["--price <model=usd>", "a model the gateway priced nothing for, priced in the report at these dollars a minute of its session (grok-voice-3.0=0.08); again for another"] as const;

// `grok-voice-3.0=0.08`: a model's id and dollars a minute. Refused here, before anything is read.
function ratesOf(said: readonly string[]): Record<string, number> {
  const rates: Record<string, number> = {};
  for (const one of said) {
    const at = one.lastIndexOf("=");
    const usd = Number(one.slice(at + 1));
    if (at <= 0 || !Number.isFinite(usd) || usd <= 0) throw new UsageError(`--price ${one}: a model and its dollars a minute, as grok-voice-3.0=0.08`);
    rates[one.slice(0, at)] = usd;
  }
  return rates;
}
/** The gate held under a condition too, said again for each: it turns `--gate` on. */
export const GATE_UNDER = ["--gate-under <condition>", "exit 1 unless one setup clears both bars under this condition too, beside the first one's line; again for another; turns --gate on"] as const;

function inputOf(comparisons: string[], out: string, flags: ReportFlags, conditions: readonly service.Condition[] = []): service.BenchmarkInput {
  const under = flags.gateUnder ?? [];
  const unknown = under.find((name) => !conditions.some((condition) => condition.name === name));
  // Refused here, before a call is placed or read: a gate on a condition nobody named would pass by saying nothing.
  if (unknown !== undefined) throw new UsageError(conditions.length < 2 ? `--gate-under ${unknown} names a condition: name two or more with --condition, the first being the line the others are read against` : `--gate-under ${unknown}: the conditions are ${conditions.map((condition) => condition.name).join(", ")}`);
  return service.BenchmarkInput.parse({ comparisons, out, floor: numberOf("--floor", flags.floor), ceiling: numberOf("--ceiling", flags.ceiling), baseline: flags.baseline, gate: flags.gate === true, countedOnly: flags.countedOnly === true, rates: ratesOf(flags.price ?? []), conditions: [...conditions], gateUnder: under });
}

async function report(ctx: Context, input: service.BenchmarkInput): Promise<void> {
  ctx.io.info(`reading ${(input.conditions.length > 0 ? input.conditions.flatMap((condition) => condition.comparisons) : input.comparisons).join(", ")}: every call's log and its recording`);
  const made = await service.benchmark(ctx, input);
  // Under --json the answer is report.json itself, the object a pipeline reads.
  ctx.io.result(made.report, () => render.benchmark(made));
  service.requireCleared(made, input);
}

/** Whether the line names a flag of the report with no report asked for. */
export function namesTheReport(flags: ReportFlags): boolean {
  return flags.floor !== undefined || flags.ceiling !== undefined || flags.baseline !== undefined || flags.gate === true || flags.countedOnly === true || (flags.price ?? []).length > 0 || (flags.gateUnder ?? []).length > 0;
}

// A benchmark is a comparison's: one caller under the agent's own settings, rung once, is placed as a
// comparison of one call so that it has a table to report. Its calls' table is what a person reads
// while waiting (stderr); the report is the verb's one answer.
/** `simulate --report`: the calls placed and followed as a comparison, then its report written. */
export async function benchmarkTheRun(ctx: Context, agent: string, input: service.SimulateInput, against: readonly api.AgentValues[], out: string, flags: ReportFlags, conditions: readonly service.Condition[] = []): Promise<void> {
  // Refused before a call is placed: a floor that is no share, or a line a condition may not have, must not cost a run.
  const wanted = inputOf(["cmp_pending"], out, flags, conditions);
  if (conditions.length < 2) {
    const done = await placeComparison(ctx, agent, input, against);
    for (const line of render.comparison(done)) ctx.io.info(line);
    await report(ctx, { ...wanted, comparisons: [done.comparison], conditions: [] });
    return;
  }
  // A condition is a comparison of its own, the same callers under the same setups, and they are placed
  // one after another: the org's calls at once and the seats that play the callers are shared, so two
  // conditions placed together would each be played under the other's load, and a room that keeps its
  // calls on the line to their ceiling would hold the clean line's seats.
  const lines = conditions.map((condition) => service.inputUnder(input, condition));
  const played: service.Condition[] = [];
  for (const [at, condition] of conditions.entries()) {
    ctx.io.print(`${condition.name} · ${service.sayLine(condition.line)}`);
    const done = await placeComparison(ctx, agent, lines[at] as service.SimulateInput, against);
    for (const line of render.comparison(done)) ctx.io.info(line);
    played.push({ ...condition, comparisons: [done.comparison] });
  }
  await report(ctx, { ...wanted, comparisons: played.flatMap((condition) => condition.comparisons), conditions: played });
}

export function registerBenchmark(program: Command, ctx: Context): void {
  const verb = program
    .command("benchmark")
    .description("the report of comparisons already played: each setup against two bars, every call with its recording and its log")
    .argument("[comparison...]", "the comparisons, as pinecall simulate named them (cmp_…): several are one table")
    .option("--condition <name:comparisons>", "the comparisons played under one condition, as television-20:cmp_…,cmp_…; again for each, the first being the line the others are read against", repeated)
    .option("--out <dir>", "the folder the report is written into", A_FOLDER);
  for (const [flag, says] of REPORT_FLAGS) verb.option(flag, says);
  verb.option(GATE_UNDER[0], GATE_UNDER[1], repeated);
  verb.option(PRICE[0], PRICE[1], repeated);
  verb.addHelpText("after", HELP.benchmark).action(async (comparisons, flags) => {
    const read = flags as ReportFlags & { out: string; condition?: string[] };
    const conditions = (read.condition ?? []).map(service.parsePlayed);
    service.requireTold(conditions);
    if (conditions.length > 0 && comparisons.length > 0) throw new UsageError("a comparison is named under its condition, or alone: with --condition, every one goes in one, as clean:cmp_…");
    if (conditions.length === 0 && comparisons.length === 0) throw new UsageError("name a comparison: pinecall simulate prints it as it places the calls");
    await report(ctx, inputOf(conditions.length > 0 ? conditions.flatMap((condition) => condition.comparisons) : comparisons, read.out, read, conditions));
  });
}
