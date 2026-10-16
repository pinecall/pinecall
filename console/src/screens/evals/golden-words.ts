/** A golden said as a transcript: each turn's input, each step that must follow it as a sentence, and — given a run's scores — where each held or broke. */

import type { Expect, Golden, Reply, Step, Turn } from "@pinecall/core/wire/rest-goldens";

/** The one word a check, a step or a turn reads as: held, broke, skipped (judged nothing), or not played (after the break). */
export type State = "held" | "broke" | "skipped" | "not played";

/** One verdict of a run's cell, as the matrix keeps it. */
export interface Scored {
  metric: string;
  passed: boolean;
  reason: string;
}

/** One line under a turn, or one final check: what must happen, and — after a run — whether it did. */
export interface Line {
  said: string;
  state?: State | undefined;
  /** The judge's own reason, kept where the line broke. */
  why?: string | undefined;
}

/** What a turn began with: the caller's line, the backend's fact, or nothing the page knows (a run read without its golden). */
export type Input = { say: string } | { event: string; data: Record<string, unknown> } | null;

/** One turn read: its number from 1, its input, the lines that follow it, and its own state after a run. */
export interface TurnRead {
  number: number;
  input: Input;
  lines: Line[];
  state?: State | undefined;
}

/** A golden read whole: its turns in order, then the checks of its final expect. */
export interface Read {
  turns: TurnRead[];
  finals: Line[];
}

const TURN_METRIC = /^t(\d+)\.(.+)$/;

const ENDED_BY = { caller: "the caller ends the call", agent: "the agent ends the call", supervisor: "a supervisor ends the call", platform: "the platform ends the call" } as const;

/** A step as a plain sentence: "calls find_slots with day 2026-10-14 · within 1.5 s". */
export function stepWords(step: Step): string {
  if ("tool" in step) return `calls ${step.tool}${argsWords(step.args)}${withinWords(step.within_ms)}`;
  if ("no_tool" in step) return `never calls ${step.no_tool}`;
  if ("reply" in step) return replyWords(step.reply);
  if ("end" in step) return ENDED_BY[step.end];
  return "nothing else happens";
}

/** The checks of a golden's final expect, one per metric the run scores them under. */
export function finalChecks(expect: Expect): { metric: string; said: string }[] {
  const checks: { metric: string; said: string }[] = [];
  if ((expect.tools ?? []).length > 0) checks.push({ metric: "tools", said: `calls ${(expect.tools ?? []).join(", ")}` });
  if ((expect.not_tools ?? []).length > 0) checks.push({ metric: "not_tools", said: `never calls ${(expect.not_tools ?? []).join(", ")}` });
  if ((expect.not ?? []).length > 0) checks.push({ metric: "silence", said: `never says ${quoted(expect.not ?? [])}` });
  if ((expect.says ?? []).length > 0) checks.push({ metric: "says", said: `says ${quoted(expect.says ?? [])}` });
  if ((expect.says_any ?? []).length > 0) checks.push({ metric: "says_any", said: `says one of ${quoted(expect.says_any ?? [])}` });
  if (expect.grounded === true) checks.push({ metric: "grounded", said: "states no price, hour, date or name the call did not carry" });
  if (expect.register !== undefined && expect.register !== null) checks.push({ metric: "register", said: `addresses the caller as ${expect.register}` });
  const named = new Set(checks.map((check) => check.metric));
  for (const judge of expect.judges ?? []) if (!named.has(judge)) checks.push({ metric: judge, said: `${judge} holds when asked again` });
  return checks;
}

/** The metric names a turn's steps are scored under, step by step (a reply with an intent is two), numbered as the runtime numbers a repeat; an event's turn has none. */
export function metricsOf(turn: Turn, number: number): string[][] {
  const seen = new Map<string, number>();
  const named = (bare: string): string => {
    const count = (seen.get(bare) ?? 0) + 1;
    seen.set(bare, count);
    return `t${number}.${bare}${count === 1 ? "" : `#${count}`}`;
  };
  return (turn.then ?? []).map((step) => {
    if ("tool" in step) return [named(`tool:${step.tool}`)];
    if ("no_tool" in step) return [named(`no_tool:${step.no_tool}`)];
    if ("reply" in step) return step.reply.intent === undefined || step.reply.intent === null ? [named("reply")] : [named("reply"), named("intent")];
    if ("end" in step) return [named("end")];
    return [named("nothing_else")];
  });
}

/**
 * A golden as a transcript; with a cell's scores, where each step held or broke. The first turn
 * that broke cuts the golden: every turn after it is not played, and the final checks are skipped.
 * A score the golden does not name (it was edited since the run) is kept, said by its metric.
 */
export function readGolden(golden: Golden, scores?: readonly Scored[]): Read {
  const by = new Map((scores ?? []).map((score) => [score.metric, score]));
  const used = new Set<string>();
  const take = (metric: string): Scored | undefined => {
    const found = by.get(metric);
    if (found !== undefined) used.add(metric);
    return found;
  };
  const turns = (golden.turns ?? []).map((turn, at): TurnRead => {
    const number = at + 1;
    const steps = metricsOf(turn, number);
    const lines = (turn.then ?? []).map((step, index): Line => {
      const scored = (steps[index] ?? []).map(take).filter((one) => one !== undefined);
      return lineOf(stepWords(step), scores === undefined ? undefined : scored);
    });
    return { number, input: inputOf(turn), lines };
  });
  const finals = finalChecks(golden.expect ?? {}).map((check): Line => lineOf(check.said, scores === undefined ? undefined : [take(check.metric)].filter((one) => one !== undefined)));
  const read = { turns, finals };
  if (scores === undefined) return read;
  const rest = scores.filter((score) => !used.has(score.metric));
  return cut(withRest(read, rest));
}

/** A run's cell read with no golden beside it: the turns its metrics name, and the final checks after. */
export function readScores(scores: readonly Scored[]): Read {
  return cut(withRest({ turns: [], finals: [] }, scores));
}

/** Where the cell broke, in a few words: "turn 2 · calls book", "the final checks", or null where everything held. */
export function brokeAt(read: Read): string | null {
  const turn = read.turns.find((one) => one.state === "broke");
  if (turn !== undefined) {
    const line = turn.lines.find((one) => one.state === "broke");
    return `turn ${turn.number}${line === undefined ? "" : ` · ${line.said}`}`;
  }
  return read.finals.some((one) => one.state === "broke") ? "the final checks" : null;
}

function lineOf(said: string, scored: readonly Scored[] | undefined): Line {
  if (scored === undefined) return { said };
  if (scored.length === 0) return { said, state: "skipped" };
  const broke = scored.find((one) => !one.passed);
  return broke === undefined ? { said, state: "held" } : { said, state: "broke", why: broke.reason };
}

// The scores no step of the golden claimed: a turn's under its number, the rest among the final checks.
function withRest(read: Read, rest: readonly Scored[]): Read {
  const turns = [...read.turns];
  const finals = [...read.finals];
  for (const score of rest) {
    const found = TURN_METRIC.exec(score.metric);
    const line = lineOf(found === null ? metricWords(score.metric) : metricWords(found[2] ?? ""), [score]);
    if (found === null) {
      finals.push(line);
      continue;
    }
    const number = Number(found[1]);
    let turn = turns.find((one) => one.number === number);
    if (turn === undefined) {
      turn = { number, input: null, lines: [] };
      turns.push(turn);
    }
    turn.lines.push(line);
  }
  turns.sort((one, other) => one.number - other.number);
  return { turns, finals };
}

// Each turn's own state; after the first that broke, every turn is not played and its lines unjudged.
function cut(read: Read): Read {
  let broken = false;
  const turns = read.turns.map((turn): TurnRead => {
    if (broken) return { ...turn, state: "not played", lines: turn.lines.map((line) => ({ said: line.said })) };
    const judged = turn.lines.some((line) => line.state === "held" || line.state === "broke");
    const state: State = turn.lines.some((line) => line.state === "broke") ? "broke" : judged || turn.lines.length === 0 ? "held" : "not played";
    if (state !== "held") broken = true;
    return { ...turn, state };
  });
  const finals = broken ? read.finals.map((line) => ({ said: line.said, state: "skipped" as const })) : read.finals;
  return { turns, finals };
}

// A metric said in words when no golden says it: `tool:book` is "calls book".
function metricWords(metric: string): string {
  const bare = metric.replace(/#\d+$/, "");
  if (bare.startsWith("tool:")) return `calls ${bare.slice("tool:".length)}`;
  if (bare.startsWith("no_tool:")) return `never calls ${bare.slice("no_tool:".length)}`;
  const said: Record<string, string> = {
    reply: "replies",
    intent: "replies as intended",
    end: "the call ends",
    nothing_else: "nothing else happens",
    tools: "calls every tool named",
    not_tools: "never calls the tools named",
    silence: "never says the phrases named",
    says: "says every phrase named",
    says_any: "says one of the phrases named",
    grounded: "states no price, hour, date or name the call did not carry",
    register: "addresses the caller as asked",
  };
  return said[bare] ?? `${bare} holds`;
}

function inputOf(turn: Turn): Input {
  if (turn.event !== undefined && turn.event !== null) return { event: turn.event.name, data: turn.event.data ?? {} };
  return { say: turn.say ?? "" };
}

function replyWords(reply: Reply): string {
  const parts: string[] = [];
  if ((reply.says ?? []).length > 0) parts.push(`saying ${quoted(reply.says ?? [])}`);
  if ((reply.says_any ?? []).length > 0) parts.push(`saying one of ${quoted(reply.says_any ?? [])}`);
  if ((reply.not ?? []).length > 0) parts.push(`never saying ${quoted(reply.not ?? [])}`);
  const said = `replies${parts.length === 0 ? "" : ` ${parts.join(", ")}`}${withinWords(reply.within_ms)}`;
  if (reply.intent === undefined || reply.intent === null) return said;
  return parts.length === 0 && (reply.within_ms ?? null) === null ? `replies: ${reply.intent}` : `${said} — and: ${reply.intent}`;
}

function argsWords(args: Record<string, unknown> | null | undefined): string {
  const pairs = Object.entries(args ?? {}).map(([key, value]) => `${key} ${valueWords(value)}`);
  return pairs.length === 0 ? "" : ` with ${pairs.join(", ")}`;
}

function withinWords(ms: number | null | undefined): string {
  return ms === undefined || ms === null ? "" : ` · within ${String(Math.round(ms / 100) / 10)} s`;
}

/** A value of a tool's arguments or an event's data, as a person reads it. */
export function valueWords(value: unknown): string {
  return typeof value === "string" ? value : JSON.stringify(value);
}

function quoted(phrases: readonly string[]): string {
  return phrases.map((phrase) => `“${phrase}”`).join(", ");
}
