/** `pinecall benchmark`: the report of comparisons already played, and the same asked of a simulation as it ends with `--report`. */

import type { Command } from "@commander-js/extra-typings";

import type * as api from "../../api/evals.js";
import type { Context } from "../../context.js";
import { UsageError } from "../../errors.js";
import { numberOf } from "../../kit/flags.js";
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
}

/** The report's flags, said once for both verbs. */
export const REPORT_FLAGS: readonly (readonly [string, string])[] = [
  ["--floor <share>", "the share of counted calls a setup must complete, 0 to 1 (0.9)"],
  ["--ceiling <seconds>", "the middle reply a setup may take, in seconds (1.5)"],
  ["--baseline <report.json>", "an earlier report: each setup is held against its own row there"],
  ["--gate", "exit 1 when no setup clears both bars, or one fell against the baseline"],
];

function inputOf(comparisons: string[], out: string, flags: ReportFlags): service.BenchmarkInput {
  return service.BenchmarkInput.parse({ comparisons, out, floor: numberOf("--floor", flags.floor), ceiling: numberOf("--ceiling", flags.ceiling), baseline: flags.baseline, gate: flags.gate === true });
}

async function report(ctx: Context, input: service.BenchmarkInput): Promise<void> {
  ctx.io.info(`reading ${input.comparisons.join(", ")}: every call's log and its recording`);
  const made = await service.benchmark(ctx, input);
  // Under --json the answer is report.json itself, the object a pipeline reads.
  ctx.io.result(made.report, () => render.benchmark(made));
  service.requireCleared(made, input);
}

/** Whether the line names a flag of the report with no report asked for. */
export function namesTheReport(flags: ReportFlags): boolean {
  return flags.floor !== undefined || flags.ceiling !== undefined || flags.baseline !== undefined || flags.gate === true;
}

// A benchmark is a comparison's: one caller under the agent's own settings, rung once, is placed as a
// comparison of one call so that it has a table to report. Its calls' table is what a person reads
// while waiting (stderr); the report is the verb's one answer.
/** `simulate --report`: the calls placed and followed as a comparison, then its report written. */
export async function benchmarkTheRun(ctx: Context, agent: string, input: service.SimulateInput, against: readonly api.AgentValues[], out: string, flags: ReportFlags): Promise<void> {
  // Refused before a call is placed: a floor that is no share must not cost a run.
  const wanted = inputOf(["cmp_pending"], out, flags);
  const done = await placeComparison(ctx, agent, input, against);
  for (const line of render.comparison(done)) ctx.io.info(line);
  await report(ctx, { ...wanted, comparisons: [done.comparison] });
}

export function registerBenchmark(program: Command, ctx: Context): void {
  const verb = program
    .command("benchmark")
    .description("the report of comparisons already played: each setup against two bars, every call with its recording and its log")
    .argument("<comparison...>", "the comparisons, as pinecall simulate named them (cmp_…): several are one table")
    .option("--out <dir>", "the folder the report is written into", A_FOLDER);
  for (const [flag, says] of REPORT_FLAGS) verb.option(flag, says);
  verb.addHelpText("after", HELP.benchmark).action(async (comparisons, flags) => {
    const read = flags as ReportFlags & { out: string };
    if (comparisons.length === 0) throw new UsageError("name a comparison: pinecall simulate prints it as it places the calls");
    await report(ctx, inputOf(comparisons, read.out, read));
  });
}
