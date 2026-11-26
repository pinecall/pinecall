/** A benchmark as a terminal reads it: the verdict, a row a setup against the two bars, what was left out, and where the report was written. */

import { BROKEN, HELD } from "../../judging/render.js";
import { count, formatHint } from "../../kit/format.js";
import { table } from "../../kit/table.js";
import type { Benchmarked } from "../service/benchmark.js";
import type { Setup, Shift, Under } from "../service/scorecard.js";

const percent = (share: number | null): string => (share === null ? "" : `${String(Math.round(share * 100))}%`);
const seconds = (value: number | null): string => (value === null ? "" : value >= 1 ? `${value.toFixed(2)} s` : `${String(Math.round(value * 1000))} ms`);
const dollars = (value: number | null): string => (value === null ? "" : `$${value.toFixed(4)}`);

/** How a setup stands against the bars: held, broken, and which one it misses. */
function standing(setup: Setup): string {
  if (setup.thin) return "most of its calls not counted";
  if (setup.clears.floor === null) return "not judged";
  const missed = [...(setup.clears.floor ? [] : ["the floor"]), ...(setup.clears.ceiling === false ? ["the ceiling"] : [])];
  return missed.length === 0 ? HELD : `${BROKEN} misses ${missed.join(" and ")}`;
}

function movedOf(setup: Setup): string {
  const was = setup.baseline;
  if (was === undefined || was.share_change === null) return "";
  const points = Math.round(was.share_change * 100);
  return `${points >= 0 ? "+" : ""}${String(points)} pts${was.regressed ? " · regressed" : ""}`;
}

/** A number a condition moved, as a cell says it: what it is under the condition. */
export function shiftOf(shift: Shift): string {
  if (shift.what === "word error") return shift.now > 1 ? "more words heard than said" : `${String(Math.round(shift.now * 100))}% word error`;
  return `${shift.now >= 10 ? String(Math.round(shift.now)) : shift.now.toFixed(1)} ${shift.what}`;
}

// A cell of the conditions' table: what the setup completed there, whether it clears both bars, and what the line moved most.
function cellOf(its: Under | undefined): string {
  if (its === undefined || its.calls === 0) return its !== undefined && its.not_counted > 0 ? `none counted (${String(its.not_counted)} not)` : "no call";
  const done = `${String(its.completed.completed)}/${String(its.completed.of)}`;
  if (its.thin) return `${done} (${String(its.not_counted)} not counted)`;
  const clears = its.clears.floor === null ? "" : its.clears.floor && its.clears.ceiling !== false ? ` ${HELD}` : ` ${BROKEN}`;
  const most = its.moved?.most[0];
  return `${done}${clears}${most === undefined ? "" : ` · ${shiftOf(most)}`}`;
}

/** The benchmark: its header, the setups best first, the verdict, the calls that do not count, and the folder. */
export function benchmark(made: Benchmarked): string[] {
  const report = made.report;
  const counted = report.calls.filter((call) => call.not_counted === null).length;
  const held = report.setups.some((setup) => setup.baseline !== undefined);
  const lines = [`${report.agent} · ${count(counted, "call")} counted · the floor ${percent(report.bars.floor)} completed · the ceiling ${String(report.bars.ceiling_s)} s a reply`];
  lines.push(
    ...table(
      ["the agent runs on", "completed", "plausibly", "reply", "p90", "a completed call", "bars", ...(held ? ["vs baseline"] : [])],
      report.setups.map((setup) => [
        setup.name,
        `${String(setup.completed.completed)} of ${String(setup.completed.of)}${setup.completed.share === null ? "" : ` · ${percent(setup.completed.share)}`}`,
        setup.completed.low === null ? "" : `${percent(setup.completed.low)}–${percent(setup.completed.high)}`,
        seconds(setup.reply.p50),
        seconds(setup.reply.p90),
        setup.cost.per_completed === null ? "none completed" : `${dollars(setup.cost.per_completed)}${setup.cost.unpriced.length > 0 ? " (not all priced)" : ""}`,
        standing(setup),
        ...(held ? [movedOf(setup)] : []),
      ]),
    ),
  );
  // The same callers under the same setups on each line, the first being the one the table above is of.
  if (report.conditions.length > 0) {
    lines.push(`under each condition, the calls completed (${report.conditions.map((one) => (one.says === "" ? one.name : `${one.name}: ${one.says}`)).join(" · ")})`);
    lines.push(...table(["the agent runs on", ...report.conditions.map((one) => one.name)], report.setups.map((setup) => [setup.name, ...report.conditions.map((one) => cellOf(setup.under?.find((its) => its.condition === one.name)))])));
  }
  lines.push(report.verdict.says);
  const out = report.calls.filter((call) => call.not_counted !== null);
  // One line a setup and a reason: seventeen calls two vendors failed for two reasons were once said
  // under the first one's words (2026-11-26).
  const reasons = new Map<string, number>();
  for (const call of out) {
    const said = `${call.setup}${call.condition === undefined ? "" : ` under ${call.condition}`} (${call.not_counted?.kind ?? ""}): ${call.not_counted?.why ?? ""}`;
    reasons.set(said, (reasons.get(said) ?? 0) + 1);
  }
  for (const [said, calls] of [...reasons].sort((one, other) => other[1] - one[1])) lines.push(`not counted, ${count(calls, "call")} of ${said}`);
  if (report.on_the_line > 0) lines.push(`${count(report.on_the_line, "call")} still on the line: in none of this`);
  if (made.folder !== null) lines.push(formatHint(`open ${made.folder}/index.html`, "report.json beside it holds every number"));
  return lines;
}
