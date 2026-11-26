/** A benchmark's conditions: the same callers under the same setups on several lines, each read against the first. */

import type { AgentValues } from "../../api/evals.js";
import { UsageError } from "../../errors.js";
import { movedSince, setupOf, type Bars, type BenchCall, type Setup, type Shift, type Under } from "./scorecard.js";
import { SimulateInput } from "./simulation.js";

/** What a condition may change of the line, each as `simulate`'s own flag names it, and the input it sets. */
const KNOBS = {
  ambience: "ambience",
  "background-noise": "backgroundNoise",
  "packet-loss": "packetLoss",
  delay: "delayMs",
  jitter: "jitterMs",
  rate: "rateKbps",
  via: "via",
} as const;
type Knob = keyof typeof KNOBS;
const WORDED = new Set<Knob>(["ambience", "via"]);

/** A line as its condition names it: `{ ambience: "television", "background-noise": 20 }`; nothing is the line as the callers have it. */
export type Line = Partial<Record<Knob, string | number>>;

/** One condition of a benchmark: its name, the line when this command set it, and the comparisons played under it. */
export interface Condition {
  name: string;
  /** Null for comparisons played before: a comparison does not say the line it was placed on. */
  line: Line | null;
  comparisons: string[];
}

const A_NAME = /^[a-z0-9][a-z0-9-]*$/;
const A_CONDITION = `--condition takes a name, and after a colon what the line is under it as knob=value pairs joined by commas — ${Object.keys(KNOBS).join(", ")} — as in television-20:ambience=television,background-noise=20; a name alone is the line as it is`;
const A_PLAYED = "--condition takes a name and, after a colon, the comparisons played under it: television-20:cmp_4f1c2a9be07d,cmp_91aa03c7d2e1";

function named(word: string, usage: string): { name: string; rest: string | null } {
  const at = word.indexOf(":");
  const name = (at < 0 ? word : word.slice(0, at)).trim();
  if (!A_NAME.test(name)) throw new UsageError(usage);
  return { name, rest: at < 0 ? null : word.slice(at + 1).trim() };
}

/** `television-20:ambience=television,background-noise=20` as a condition to place: its name and its line. */
export function parseCondition(word: string): Condition {
  const { name, rest } = named(word, A_CONDITION);
  const line: Line = {};
  for (const pair of rest === null || rest === "" ? [] : rest.split(",")) {
    const at = pair.indexOf("=");
    const knob = pair.slice(0, at).trim() as Knob;
    const value = pair.slice(at + 1).trim();
    if (at < 0 || !(knob in KNOBS) || value === "" || knob in line) throw new UsageError(A_CONDITION);
    if (!WORDED.has(knob) && !Number.isFinite(Number(value))) throw new UsageError(`--condition ${name}: ${knob} takes a number, not ${value}`);
    line[knob] = WORDED.has(knob) ? value : Number(value);
  }
  // How loud is never guessed: a room 0 dB under the caller is as loud as the caller.
  if (line.ambience !== undefined && line["background-noise"] === undefined) throw new UsageError(`--condition ${name}: an ambience says how loud it is, as ambience=${String(line.ambience)},background-noise=20 (dB under the caller)`);
  return { name, line, comparisons: [] };
}

/** `television-20:cmp_a,cmp_b` as a condition already played: its name and its comparisons. */
export function parsePlayed(word: string): Condition {
  const { name, rest } = named(word, A_PLAYED);
  const comparisons = (rest ?? "").split(",").map((id) => id.trim()).filter((id) => id !== "");
  if (comparisons.length === 0 || comparisons.some((id) => !/^cmp_[a-z0-9]+$/.test(id))) throw new UsageError(A_PLAYED);
  return { name, line: null, comparisons };
}

/** Refuses two conditions of one name: a column of the report is told from another by it. */
export function requireTold(conditions: readonly Condition[]): void {
  const twice = conditions.find((one, at) => conditions.findIndex((other) => other.name === one.name) !== at);
  if (twice !== undefined) throw new UsageError(`two conditions are named ${twice.name}: each is a column of the report, told from the others by its name`);
}

/** What a simulation takes under a condition: the run as asked, on that condition's line. */
export function inputUnder(input: SimulateInput, condition: Condition): SimulateInput {
  const line = Object.fromEntries(Object.entries(condition.line ?? {}).map(([knob, value]) => [KNOBS[knob as Knob], value]));
  const read = SimulateInput.safeParse({ ...input, ...line });
  if (!read.success) throw new UsageError(`--condition ${condition.name}: ${read.error.issues[0]?.message ?? "its line is refused"}`);
  return read.data;
}

/** A line in a few words, as a report's column says it. */
export function sayLine(line: Line | null): string {
  if (line === null) return "";
  const said: string[] = [];
  if (line["background-noise"] !== undefined || line.ambience !== undefined) said.push(`${String(line.ambience ?? "television")} ${String(line["background-noise"] ?? 0)} dB under the caller`);
  if (line["packet-loss"] !== undefined) said.push(`${String(Math.round(Number(line["packet-loss"]) * 100))}% of packets lost`);
  if (line.delay !== undefined) said.push(`${String(line.delay)} ms of delay`);
  if (line.jitter !== undefined) said.push(`${String(line.jitter)} ms of jitter`);
  if (line.rate !== undefined) said.push(`${String(line.rate)} kbps`);
  if (line.via !== undefined) said.push(`by ${String(line.via)}`);
  return said.length === 0 ? "the line as the callers have it" : said.join(" · ");
}

/** A condition as the command that places it says it. */
export function flagOf(condition: Condition): string {
  const pairs = Object.entries(condition.line ?? {}).map(([knob, value]) => `${knob}=${String(value)}`);
  return `--condition ${condition.name}${pairs.length === 0 ? "" : `:${pairs.join(",")}`}`;
}

// What a room moves is counted a call, so that a condition with fewer counted calls is read fairly, and
// each number is held against a step of its own: a turn a call, a second of reply, two minutes of a
// call, a quarter of the words. Word error has no ceiling (a television's words are all "inserted": 19
// was measured on 2026-11-26), so past one it counts as one, or it would always be what moved most.
const MOVES: readonly { what: string; of: (setup: Setup) => number | null; step: number; most?: number }[] = [
  { what: "turns nobody said a call", of: (setup) => (setup.hearing === null ? null : setup.hearing.phantom_turns / setup.hearing.calls), step: 1 },
  { what: "replies the room cut a call", of: (setup) => (setup.hearing === null ? null : (setup.hearing.cut_by_the_room + setup.hearing.cut_by_a_murmur) / setup.hearing.calls), step: 1 },
  { what: "lines nobody answered a call", of: (setup) => (setup.hearing === null ? null : setup.hearing.unanswered / setup.hearing.calls), step: 1 },
  { what: "word error", of: (setup) => setup.hearing?.word_error_rate ?? null, step: 0.25, most: 1 },
  { what: "seconds a call", of: (setup) => setup.length_s, step: 120 },
  { what: "seconds to reply", of: (setup) => setup.reply.p50, step: 1 },
];
const SAID_AT_MOST = 2;

/** What a condition moved by a step or more against the baseline's line, the most steps first. */
export function shiftsOf(now: Setup, was: Setup): Shift[] {
  const moved = MOVES.flatMap((one) => {
    const before = one.of(was);
    const after = one.of(now);
    if (before === null || after === null) return [];
    const by = Math.min(Math.abs(after - before), one.most ?? Infinity) / one.step;
    return by >= 1 ? [{ by, shift: { what: one.what, was: before, now: after } }] : [];
  });
  return moved.sort((one, other) => other.by - one.by).slice(0, SAID_AT_MOST).map((one) => one.shift);
}

/** Whether a setup's numbers clear both bars: judged, not thin, the floor held and the ceiling not missed. */
export function clearsBoth(one: Pick<Setup, "thin" | "clears">): boolean {
  return !one.thin && one.clears.floor === true && one.clears.ceiling !== false;
}

/** A setup's numbers under each condition, the baseline's first, each read against the baseline's. */
export function underEach(values: AgentValues, calls: readonly BenchCall[], conditions: readonly Condition[], callers: readonly string[], bars: Bars): { baseline: Setup; under: Under[] } {
  const each = conditions.map((condition) => setupOf(values, calls.filter((call) => call.condition === condition.name), callers, bars));
  const baseline = each[0] as Setup;
  const under = each.map((its, at): Under => ({
    condition: (conditions[at] as Condition).name,
    calls: its.calls,
    not_counted: its.not_counted,
    thin: its.thin,
    completed: its.completed,
    reply: its.reply,
    length_s: its.length_s,
    hearing: its.hearing,
    rounds: its.rounds,
    clears: its.clears,
    moved: at === 0 ? null : { ...movedSince(its, baseline), most: shiftsOf(its, baseline) },
  }));
  return { baseline, under };
}

/** The setups that clear both bars under every condition, and the sentence the verdict adds for them. */
export function heldUnderEvery(setups: readonly Setup[], conditions: readonly Condition[]): { names: string[]; says: string } {
  const names = setups.filter((setup) => (setup.under ?? []).length > 0 && (setup.under ?? []).every(clearsBoth)).map((setup) => setup.name);
  const all = conditions.map((condition) => condition.name).join(", ");
  if (names.length === 0) return { names, says: `under every condition (${all}) none clears both bars` };
  return { names, says: `under every condition (${all}) ${names.join(", ")} ${names.length === 1 ? "clears" : "clear"} both bars` };
}
