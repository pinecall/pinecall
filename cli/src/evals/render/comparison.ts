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

/** The agent's values in a few words: `thinks groq/openai/gpt-oss-120b · speaks deepgram`, `talks google/gemini-3.8-live` for a realtime model; its own settings when none. */
export function against(values: AgentValues): string {
  const pairs: [string, string | number | undefined][] = [["talks", values.realtime], ["hears", values.stt], ["thinks", values.llm], ["speaks", values.tts], ["voice", values.voice], ["language", values.language], ["temperature", values.temperature], ["end of turn", values.end_of_turn]];
  const said = pairs.flatMap(([name, value]) => (value === undefined ? [] : [`${name} ${String(value)}`]));
  return said.length === 0 ? "the agent's own settings" : said.join(" · ");
}

/** Whether a call counts: one a vendor, the platform or its own caller broke measured nothing of the agent. */
function counts(row: ComparisonRow): boolean {
  return row.valid !== false;
}

/** The judges' column of one call: a call that does not count or ended in error reads so, whatever a judge made of what little it had. */
export function verdictOf(row: ComparisonRow): string {
  if (row.ended_at === null) return "on a call";
  if (!counts(row)) return `not counted: ${row.invalid?.kind ?? "broken"}`;
  if (row.why !== null) return "never started";
  if (row.end_reason === "error") return "ended in error";
  if (row.score === null) return (row.end_reason ?? "not judged").replace(/_/g, " ");
  return `${row.score.passed ? HELD : BROKEN} ${String(row.score.held)}/${String(row.score.judged)}`;
}

// A caller's task is its goal: done when the judge of what it expected held; a caller that expects
// nothing is done when every judge held.
function didIt(row: ComparisonRow): boolean | null {
  if (row.ended_at === null || row.why !== null || !counts(row)) return null;
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
// the configuration's calls cost over the ones that did it, which a price per call never says. A call
// that does not count is no call of the configuration's: neither its cost nor its reply is summed.
/** Several runs by configuration, the one that did the most first: each caller's count, all of them, the middle reply, what they cost, and what one completed call cost. */
function byConfiguration(rows: readonly ComparisonRow[], personas: readonly string[]): string[] {
  const named = new Map<string, ComparisonRow[]>();
  for (const row of rows) named.set(against(row.against), [...(named.get(against(row.against)) ?? []), row]);
  const summed = [...named].map(([name, all]) => {
    const its = all.filter(counts);
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

/** One measure of how the calls were heard, summed over a configuration's calls that carry it. */
function heard(rows: readonly ComparisonRow[], name: string): number {
  return rows.reduce((sum, row) => sum + (row.hearing?.[name] ?? 0), 0);
}

// What a simulation knows and a real call does not: what its caller really said, and when. Read off
// each call's hearing, summed by configuration, so a table says which agent invented turns, talked over
// its caller or was cut off by the room, without opening a call.
/** How each configuration heard its callers: lines said, unanswered, turns heard that nobody said, replies cut by the room, lines talked over, the middle word error. */
function hearingByConfiguration(rows: readonly ComparisonRow[]): string[] {
  const heardRows = rows.filter((row) => counts(row) && row.hearing != null);
  if (heardRows.length === 0) return [];
  const named = new Map<string, ComparisonRow[]>();
  for (const row of heardRows) named.set(against(row.against), [...(named.get(against(row.against)) ?? []), row]);
  const errors = (its: readonly ComparisonRow[]): number | null => middle(its.flatMap((row) => (typeof row.hearing?.word_error_rate === "number" ? [row.hearing.word_error_rate] : [])));
  return [
    "how each heard its callers, against what they really said",
    ...table(
      ["the agent runs on", "lines", "unanswered", "heard nobody", "cut by the room", "talked over", "word error"],
      [...named].map(([name, its]) => [
        name,
        heard(its, "lines"),
        heard(its, "unanswered"),
        heard(its, "phantom_turns"),
        heard(its, "cut_by_the_room"),
        heard(its, "talked_over"),
        ((rate) => (rate === null ? "" : `${String(Math.round(rate * 100))}%`))(errors(its)),
      ]),
    ),
  ];
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
  lines.push(...hearingByConfiguration(found.rows));
  for (const row of found.rows) if (row.invalid != null) lines.push(`not counted, ${against(row.against)} (${row.invalid.kind}): ${row.invalid.why}`);
  for (const row of found.rows) if (row.why !== null && counts(row)) lines.push(`never started, ${against(row.against)}: ${row.why}`);
  for (const one of found.stopped ?? []) lines.push(`no more calls on ${against(one.against)}: ${one.why}`);
  // One line a setup and a reason: the calls a stopped setup still had waiting are refused alike.
  const refusals = new Map<string, number>();
  for (const one of done.refused) {
    const said = `${against(one.against)}: ${one.why}`;
    refusals.set(said, (refusals.get(said) ?? 0) + 1);
  }
  for (const [said, calls] of refusals) lines.push(calls === 1 ? `not placed, ${said}` : `not placed, ${String(calls)} calls of ${said}`);
  if (found.abandoned === true) lines.push(`${String(found.waiting ?? 0)} never placed: the gateway placing them was restarted — run it again for those`);
  lines.push(formatHint("pinecall sessions <call> reads one whole"));
  return lines;
}
