/** A run as a terminal reads it: one line per golden with where it came from, details under each that broke, the divergences, the footer. */

import { BROKEN, HELD, reasonOf } from "../../judging/render.js";
import { DECLARED, TURN_METRICS, type Cell, type EvalRun, type Latencies, type Matrix, type Medians, type Score, type SuiteReport } from "../service/index.js";

// A step of a turn names its metric `t{n}.<step>`.
const TURN_METRIC = /^t(\d+)\./;

/** The medians on one line, in milliseconds. */
export function latencyLine(medians: Medians): string {
  return TURN_METRICS.filter((name) => medians[name] !== undefined)
    .map((name) => `${name} ${Math.round(medians[name]! * 1000)}ms`)
    .join(" · ");
}

/**
 * The report of a run. `declaredAs` is shown in place of the runner's `declared` model. `files`,
 * the names sent from disk, marks each golden `file` or `case`: a golden the run has that this side
 * never sent is a case the gateway played from the dataset. Unknown (`runs show`), no mark.
 */
export function matrix(run: EvalRun, latencies: Latencies, declaredAs: string, files?: ReadonlySet<string>): string[] {
  const found = run.matrix;
  if (found === null) return [`${run.agent}  ${run.status}${run.error === null ? "" : `: ${run.error}`}`];
  const models = found.models.map((model) => named(model, declaredAs));
  const lines = [`${run.agent} · ${found.goldens.length} golden${found.goldens.length === 1 ? "" : "s"} · ${models.join(" · ")}`];
  // Grouped by model only when comparing several.
  const compared = found.models.length > 1;
  for (const model of found.models) {
    if (compared) lines.push(`  ${named(model, declaredAs)}`);
    for (const cell of found.runs.filter((one) => one.model === model)) lines.push(...cellLines(cell, callOf(run, cell), latencies, compared, originOf(cell, files)));
  }
  lines.push(...divergences(found, declaredAs), footer(run, found));
  // A failed run keeps its partial matrix; its error says the count is not complete.
  if (run.error !== null) lines.push(`  ${run.error}`);
  return lines;
}

/** The report with the reproductions written, as `test` prints it: each golden marked `file` or `case`. */
export function suite(report: SuiteReport, declaredAs: string): string[] {
  const lines = matrix(report.run, report.latencies, declaredAs, new Set(report.files));
  if (report.reproductions.length > 0) {
    const folder = report.reproductions[0]!.replace(/\/[^/]*$/, "");
    lines.push(`  ${report.reproductions.length} reproduction${report.reproductions.length === 1 ? "" : "s"} written to ${folder}/`);
  }
  return lines;
}

/** One cell's lines, the run narrowed to it: what progress draws as each golden is judged. */
export function cellOf(run: EvalRun, cell: Cell, declaredAs: string, files?: ReadonlySet<string>): string[] {
  const found = run.matrix!;
  const failures = found.failures.filter((one) => one.golden === cell.golden && one.model === cell.model);
  const narrowed: EvalRun = { ...run, matrix: { ...found, models: [cell.model], goldens: [cell.golden], runs: [cell], failures } };
  return matrix(narrowed, {}, declaredAs, files).slice(1, -1);
}

// Where the golden came from, after its name: `file` when this side sent it, `case` otherwise; nothing when nobody knows.
function originOf(cell: Cell, files: ReadonlySet<string> | undefined): string {
  if (files === undefined) return "";
  return files.has(cell.golden) ? "  file" : "  case";
}

// A passing golden is one line; a failing one adds the turn that cut it, a line per broken metric and the call id.
function cellLines(cell: Cell, call: string, latencies: Latencies, indented: boolean, origin: string): string[] {
  const pad = indented ? "    " : "  ";
  const broken = cell.scores.filter((score) => !score.passed);
  const measured = latencyLine(latencies[call] ?? {});
  if (broken.length === 0) return [`${pad}${HELD} ${cell.golden}${origin}${measured === "" ? "" : `  ${measured}`}`];
  const width = Math.max(...broken.map((score) => score.metric.length), "log".length);
  return [
    `${pad}${BROKEN} ${cell.golden}${origin}`,
    ...turnThatBroke(broken).map((turn) => `${pad}      turn ${turn} broke`),
    ...broken.map((score) => `${pad}      ${score.metric.padEnd(width)}  broken   ${reasonOf(score)}`),
    `${pad}      ${"log".padEnd(width)}           ${call}`,
  ];
}

// The first step that breaks cuts the golden: the earliest turn a broken metric names, if any.
function turnThatBroke(broken: Score[]): number[] {
  const turns = broken.map((score) => TURN_METRIC.exec(score.metric)?.[1]).filter((turn) => turn !== undefined).map(Number);
  return turns.length === 0 ? [] : [Math.min(...turns)];
}

// Goldens and metrics where models disagree.
function divergences(found: Matrix, declaredAs: string): string[] {
  if (found.models.length < 2) return [];
  const lines: string[] = [];
  for (const golden of found.goldens) {
    for (const metric of found.metrics) {
      const known = found.models.map((model) => ({ model, score: scoreAt(found, model, golden, metric) })).filter((one) => one.score !== undefined);
      if (known.length < 2 || new Set(known.map((one) => one.score!.passed)).size === 1) continue;
      lines.push(`      ${golden}  ${metric}  ${known.map((one) => `${one.score!.passed ? HELD : BROKEN} ${named(one.model, declaredAs)}`).join("   ")}`);
    }
  }
  return lines.length === 0 ? [] : ["  divergences", ...lines];
}

// Passed/total, judge calls, cost and duration.
function footer(run: EvalRun, found: Matrix): string {
  const cells = found.runs.length;
  const held = cells - new Set(found.failures.map((one) => `${one.model} ${one.golden}`)).size;
  const seconds = Math.round((run.finished_at ?? run.started_at) - run.started_at);
  const cost = found.runs.reduce((total, cell) => total + (cell.summary?.cost?.usd ?? 0), 0);
  return `  ${held}/${cells} · ${found.judge_calls} judge call${found.judge_calls === 1 ? "" : "s"} · $${cost.toFixed(4)} · ${seconds}s`;
}

function scoreAt(found: Matrix, model: string, golden: string, metric: string): Score | undefined {
  return found.runs.find((one) => one.model === model && one.golden === golden)?.scores.find((one) => one.metric === metric);
}

function callOf(run: EvalRun, cell: Cell): string {
  return run.calls.find((one) => one.golden === cell.golden && one.model === cell.model)?.call ?? "";
}

function named(model: string, declaredAs: string): string {
  return model === DECLARED ? declaredAs : model;
}
