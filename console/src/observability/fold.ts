/** What Observability says of a window, worked out of its days: the totals, where a turn's time goes, how calls ended, which judges said no, what the money went to. */

import type { Tone } from "../dashboard/charts";
import { lengthOf } from "../lib/format";
import type { Insights } from "../lib/insights";
import type { Stack, StackKey } from "./chart";
import type { SeriesDay, SeriesVendor, SlowTurn, ToolStat } from "./door";

/** The part of a tail a number is: the typical turn, or the slow one. */
export type Tail = "median_s" | "p95_s";

export type StageKey = "stt" | "llm" | "tools" | "tts";

/** A turn's stages in the order it happens, named and coloured as Configure does. */
export const STAGES: readonly { stage: StageKey; name: string; doing: string; tone: Tone }[] = [
  { stage: "stt", name: "Transcriber", doing: "Hearing", tone: "accent" },
  { stage: "llm", name: "Model", doing: "Thinking", tone: "blue" },
  { stage: "tools", name: "Tools", doing: "The tools", tone: "warn" },
  { stage: "tts", name: "Voice", doing: "Speaking", tone: "pink" },
];

/** The three a vendor answers for: tools are the org's own. */
export const VENDOR_STAGES = STAGES.filter((one) => one.stage !== "tools");

/** `850 ms`, `1.24 s`, `12 s`. */
export function took(value: number): string {
  return value < 1 ? `${Math.round(value * 1000)} ms` : value >= 10 ? `${Math.round(value)} s` : `${value.toFixed(2)} s`;
}

/** A length in seconds as `3:07`. */
export function lengthSaid(value: number): string {
  return lengthOf(0, value);
}

/** The window before the one in view, in a sentence. */
export function beforeSaid(days: number): string {
  return days === 1 ? "the day before" : `the ${days} days before`;
}

/** The window's value of a daily number, each day weighted by the calls it held. */
export function across(days: readonly SeriesDay[], pick: (day: SeriesDay) => number | null): number | null {
  const held = days.flatMap((day) => {
    const value = pick(day);
    return value === null || day.calls === 0 ? [] : [{ value, weight: day.calls }];
  });
  const weight = held.reduce((sum, one) => sum + one.weight, 0);
  return weight === 0 ? null : held.reduce((sum, one) => sum + one.value * one.weight, 0) / weight;
}

export function dayStage(day: SeriesDay, stage: string): SeriesDay["stages"][number] | undefined {
  return day.stages.find((one) => one.stage === stage);
}

export interface Totals {
  calls: number;
  held: number;
  judged: number;
  /** Seconds to answer, typical. */
  answer: number | null;
  /** Seconds to the model's first token, typical. */
  firstToken: number | null;
  length: number | null;
  spend: number;
}

export function totalsOf(rows: readonly SeriesDay[]): Totals {
  const sum = (pick: (day: SeriesDay) => number): number => rows.reduce((all, day) => all + pick(day), 0);
  const tokens = rows.flatMap((day) => {
    const llm = dayStage(day, "llm");
    return llm?.median_s == null ? [] : [{ value: llm.median_s, turns: llm.turns }];
  });
  const turns = tokens.reduce((all, one) => all + one.turns, 0);
  const finished = sum((day) => (day.mean_length_s === null ? 0 : day.finished));
  return {
    calls: sum((day) => day.calls),
    held: sum((day) => day.judges.reduce((all, judge) => all + judge.held, 0)),
    judged: sum((day) => day.judges.reduce((all, judge) => all + judge.judged, 0)),
    answer: across(rows, (day) => day.e2e_median_s),
    firstToken: turns === 0 ? null : tokens.reduce((all, one) => all + one.value * one.turns, 0) / turns,
    length: finished === 0 ? null : sum((day) => (day.mean_length_s ?? 0) * day.finished) / finished,
    spend: sum((day) => day.spend_usd),
  };
}

/** The stage's value across every vendor that carried it, each weighted by its turns, and the vendor and model that carried most. */
export function stageOf(vendors: readonly SeriesVendor[], stage: string, tail: Tail): { seconds: number; vendor: string; model: string | null } | null {
  const rows = vendors.filter((one) => one.stage === stage && one[tail] !== null);
  const turns = rows.reduce((sum, one) => sum + one.turns, 0);
  // A turn whose report named no vendor counts in the stage's value but cannot be its name.
  const top = rows.filter((one) => one.vendor !== "").sort((a, b) => b.turns - a.turns)[0];
  if (turns === 0 || top === undefined) return null;
  return { seconds: rows.reduce((sum, one) => sum + (one[tail] ?? 0) * one.turns, 0) / turns, vendor: top.vendor, model: top.model };
}

/** `deepgram · nova-3`. */
export function vendorSaid(vendor: string, model: string | null): string {
  return model === null ? vendor : `${vendor} · ${model}`;
}

/** One stage of a turn: how long it took, and who or what took it. */
export interface Part {
  stage: StageKey;
  name: string;
  doing: string;
  tone: Tone;
  seconds: number;
  by: string;
}

/** The window's turn, stage by stage. Tools are always their typical run: no tail is counted for them. */
export function partsOf(vendors: readonly SeriesVendor[], tools: readonly ToolStat[], tail: Tail): Part[] {
  const timed = tools.filter((tool) => tool.median_s !== null);
  const ran = timed.reduce((sum, tool) => sum + tool.ran, 0);
  return STAGES.flatMap((one) => {
    if (one.stage === "tools") return ran === 0 ? [] : [{ ...one, seconds: timed.reduce((sum, tool) => sum + (tool.median_s ?? 0) * tool.ran, 0) / ran, by: `${ran} ${ran === 1 ? "run" : "runs"}` }];
    const at = stageOf(vendors, one.stage, tail);
    return at === null ? [] : [{ ...one, seconds: at.seconds, by: vendorSaid(at.vendor, at.model) }];
  });
}

/** One slow turn, stage by stage; a stage that was not timed, or took nothing, is left out. */
export function slowPartsOf(turn: SlowTurn): Part[] {
  const spent: Readonly<Record<StageKey, number | null>> = { stt: turn.hears_s, llm: turn.thinks_s, tools: turn.tools_s, tts: turn.speaks_s };
  return STAGES.flatMap((one) => {
    const seconds = spent[one.stage];
    return seconds === null || seconds <= 0 ? [] : [{ ...one, seconds, by: "" }];
  });
}

const ENDING_TONES: readonly Tone[] = ["accent", "blue", "good", "warn", "pink"];
const OTHER = "other";

/** How calls ended a day at a time: the window's most common reasons each in a colour, the rest as one. */
export function endingsOf(rows: readonly SeriesDay[]): { keys: StackKey[]; stacks: Stack[] } {
  const totals = new Map<string, number>();
  for (const day of rows) for (const ending of day.endings) totals.set(ending.reason, (totals.get(ending.reason) ?? 0) + ending.count);
  const reasons = [...totals].sort((a, b) => b[1] - a[1]).map(([reason]) => reason);
  const named = reasons.slice(0, ENDING_TONES.length);
  const keys: StackKey[] = named.map((reason, at) => ({ key: reason, name: reason.replaceAll("_", " "), tone: ENDING_TONES[at] ?? "quiet" }));
  if (reasons.length > named.length) keys.push({ key: OTHER, name: "other", tone: "quiet" });
  const stacks = rows.map((day) => {
    const counts: Record<string, number> = {};
    for (const ending of day.endings) {
      const key = named.includes(ending.reason) ? ending.reason : OTHER;
      counts[key] = (counts[key] ?? 0) + ending.count;
    }
    return { day: day.day, counts };
  });
  return { keys, stacks };
}

/** The judges that said no in the window, the one that said it most first. */
export function failuresOf(rows: readonly SeriesDay[]): { name: string; broken: number; judged: number }[] {
  const said = new Map<string, { broken: number; judged: number }>();
  for (const day of rows)
    for (const judge of day.judges) {
      const was = said.get(judge.name) ?? { broken: 0, judged: 0 };
      said.set(judge.name, { broken: was.broken + (judge.judged - judge.held), judged: was.judged + judge.judged });
    }
  return [...said].map(([name, one]) => ({ name, ...one })).filter((one) => one.broken > 0).sort((a, b) => b.broken - a.broken);
}

type Spend = Insights["agents"][number]["spend"];

export function spendTotal(spend: Spend): number {
  return spend.llm_usd + spend.stt_usd + spend.tts_usd + spend.phone_usd + spend.platform_usd;
}

/** What the window's money went to, over every agent counted: the three stages in Configure's colours, then the phone and the platform where they cost. */
export function spendSplit(agents: Insights["agents"]): { name: string; value: number; tone: "accent" | "blue" | "pink" | "warn" | "good" }[] {
  const sum = (pick: (spend: Spend) => number): number => agents.reduce((all, one) => all + pick(one.spend), 0);
  const phone = sum((spend) => spend.phone_usd);
  const platform = sum((spend) => spend.platform_usd);
  return [
    { name: "Transcriber", value: sum((spend) => spend.stt_usd), tone: "accent" },
    { name: "Model", value: sum((spend) => spend.llm_usd), tone: "blue" },
    { name: "Voice", value: sum((spend) => spend.tts_usd), tone: "pink" },
    ...(phone > 0 ? [{ name: "Phone", value: phone, tone: "warn" as const }] : []),
    ...(platform > 0 ? [{ name: "Platform", value: platform, tone: "good" as const }] : []),
  ];
}
