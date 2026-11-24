/** A comparison as a terminal reads it: one row a call, then several runs summed by configuration with what a completed call cost. */

import type { AgentValues, ComparisonRow } from "../../api/evals.js";
import { BROKEN, HELD } from "../../judging/render.js";
import { count, formatHint } from "../../kit/format.js";
import { table } from "../../kit/table.js";
import type { Compared } from "../service/comparison.js";

/** Seconds as the table says them: 1.24 s, 480 ms; nothing for a measure no turn took. */
function seconds(value: number | null): string {
  if (value === null) return "";
  return value >= 1 ? `${value.toFixed(2)} s` : `${String(Math.round(value * 1000))} ms`;
}

/** The agent's values in a few words: `thinks groq/openai/gpt-oss-120b · speaks deepgram`; its own settings when none. */
export function against(values: AgentValues): string {
  const pairs: [string, string | number | undefined][] = [["hears", values.stt], ["thinks", values.llm], ["speaks", values.tts], ["voice", values.voice], ["language", values.language], ["temperature", values.temperature], ["end of turn", values.end_of_turn]];
  const said = pairs.flatMap(([name, value]) => (value === undefined ? [] : [`${name} ${String(value)}`]));
  return said.length === 0 ? "the agent's own settings" : said.join(" · ");
}

/** The judges' column of one call: a call that ended in error reads so, whatever a judge made of what little it had. */
export function verdictOf(row: ComparisonRow): string {
  if (row.ended_at === null) return "on a call";
  if (row.why !== null) return "never started";
  if (row.end_reason === "error") return "ended in error";
  if (row.score === null) return (row.end_reason ?? "not judged").replace(/_/g, " ");
  return `${row.score.passed ? HELD : BROKEN} ${String(row.score.held)}/${String(row.score.judged)}`;
}

// A caller's task is its goal: done when the judge of what it expected held; a caller that expects
// nothing is done when every judge held.
function didIt(row: ComparisonRow): boolean | null {
  if (row.ended_at === null || row.why !== null) return null;
  if (row.goal !== undefined && row.goal !== null) return row.goal === "held";
  return row.score === null ? null : row.score.passed;
}

/** The middle value of the measures taken; none when no call took one. */
function middle(values: readonly number[]): number | null {
  if (values.length === 0) return null;
  const sorted = [...values].sort((one, other) => one - other);
  const half = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 1 ? (sorted[half] ?? null) : ((sorted[half - 1] ?? 0) + (sorted[half] ?? 0)) / 2;
}

/** `4 of 5`: how many of the runs judged did the caller's task. */
function share(did: readonly (boolean | null)[]): string {
  const judged = did.filter((one) => one !== null);
  return `${String(judged.filter((one) => one).length)} of ${String(judged.length)}`;
}

// A call that did not do the caller's task was paid for too: what a completed call cost is everything
// the configuration's calls cost over the ones that did it, which a price per call never says.
/** Several runs by configuration, the one that did the most first: each caller's count, all of them, the middle reply, what they cost, and what one completed call cost. */
function byConfiguration(rows: readonly ComparisonRow[], personas: readonly string[]): string[] {
  const named = new Map<string, ComparisonRow[]>();
  for (const row of rows) named.set(against(row.against), [...(named.get(against(row.against)) ?? []), row]);
  const summed = [...named].map(([name, its]) => {
    const did = its.map(didIt);
    const judged = did.filter((one) => one !== null).length;
    const done = did.filter((one) => one === true).length;
    const cost = its.reduce((sum, row) => sum + (row.cost_usd ?? 0), 0);
    return { name, its, did, judged, done, cost, each: done === 0 ? null : cost / done };
  });
  summed.sort((one, other) => other.done / (other.judged || 1) - one.done / (one.judged || 1) || (one.each ?? Infinity) - (other.each ?? Infinity));
  const several = personas.length > 1;
  const lines = [several ? "how often each did the callers' tasks, and what a completed call cost" : "how often each did the caller's task, and what a completed call cost"];
  lines.push(
    ...table(
      ["the agent runs on", ...(several ? personas : []), several ? "all" : "did it", "reply", "cost", "a completed call"],
      summed.map((one) => [
        one.name,
        ...(several ? personas.map((persona) => share(one.its.filter((row) => row.persona === persona).map(didIt))) : []),
        `${share(one.did)}${one.judged === 0 ? "" : ` · ${String(Math.round((100 * one.done) / one.judged))}%`}`,
        seconds(middle(one.its.flatMap((row) => (row.latency.e2e_latency === null ? [] : [row.latency.e2e_latency])))),
        `$${one.cost.toFixed(4)}`,
        one.each === null ? "none completed" : `$${one.each.toFixed(4)}`,
      ]),
    ),
  );
  return lines;
}

/** A comparison: the callers against the agent, one row per call, then several runs summed by configuration, what was not placed, and how to read a call whole. */
export function comparison(done: Compared): string[] {
  const found = done.table;
  const callers = found.personas.length > 0 ? found.personas : [found.persona];
  const several = callers.length > 1;
  const lines = [`${callers.join(", ")} against ${found.agent} · ${count(found.rows.length, "call")} · ${several ? "caller by caller, each one's best first" : "best first"}`];
  lines.push(
    ...table(
      ["#", ...(several ? ["caller"] : []), "the agent runs on", "judges", "reply", "thinks", "speaks", "hears", "cost", "length", "call"],
      found.rows.map((row, index) => [
        index + 1,
        ...(several ? [row.persona] : []),
        against(row.against),
        verdictOf(row),
        seconds(row.latency.e2e_latency),
        seconds(row.latency.llm_node_ttft),
        seconds(row.latency.tts_node_ttfb),
        seconds(row.latency.transcription_delay),
        row.cost_usd === null ? "" : `$${row.cost_usd.toFixed(4)}`,
        row.ended_at === null ? "" : `${String(Math.round(row.ended_at - row.started_at))} s`,
        row.call,
      ]),
    ),
  );
  if ((found.repeats ?? 1) > 1 || several) lines.push(...byConfiguration(found.rows, callers));
  for (const row of found.rows) if (row.why !== null) lines.push(`never started, ${against(row.against)}: ${row.why}`);
  for (const one of done.refused) lines.push(`not placed, ${against(one.against)}: ${one.why}`);
  if (found.abandoned === true) lines.push(`${String(found.waiting ?? 0)} never placed: the gateway placing them was restarted — run it again for those`);
  lines.push(formatHint("pinecall sessions <call> reads one whole"));
  return lines;
}
