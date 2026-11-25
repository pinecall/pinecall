/** A benchmark as a terminal reads it: the verdict, a row a setup against the two bars, what was left out, and where the report was written. */

import { BROKEN, HELD } from "../../judging/render.js";
import { count, formatHint } from "../../kit/format.js";
import { table } from "../../kit/table.js";
import type { Benchmarked } from "../service/benchmark.js";
import type { Setup } from "../service/scorecard.js";

const percent = (share: number | null): string => (share === null ? "" : `${String(Math.round(share * 100))}%`);
const seconds = (value: number | null): string => (value === null ? "" : value >= 1 ? `${value.toFixed(2)} s` : `${String(Math.round(value * 1000))} ms`);
const dollars = (value: number | null): string => (value === null ? "" : `$${value.toFixed(4)}`);

/** How a setup stands against the bars: held, broken, and which one it misses. */
function standing(setup: Setup): string {
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
  lines.push(report.verdict.says);
  const out = report.calls.filter((call) => call.not_counted !== null);
  for (const kind of ["vendor", "platform", "caller"] as const) {
    const its = out.filter((call) => call.not_counted?.kind === kind);
    if (its.length > 0) lines.push(`not counted, ${count(its.length, "call")} (${kind}): ${its[0]?.not_counted?.why ?? ""}`);
  }
  if (report.on_the_line > 0) lines.push(`${count(report.on_the_line, "call")} still on the line: in none of this`);
  if (made.folder !== null) lines.push(formatHint(`open ${made.folder}/index.html`, "report.json beside it holds every number"));
  return lines;
}
