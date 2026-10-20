/** What Time to answer is made of: the window's value read off the days, and the stages it divides into. */

import type { SeriesDay, SeriesVendor } from "../../lib/series";
import type { ToolStat } from "../../lib/tools";

/** The part of a tail a stage's number is: the typical turn, or the slow one. */
export type Tail = "median_s" | "p95_s";

/** The window's value of a daily number, each day weighted by the calls it held. */
export function across(days: readonly SeriesDay[], pick: (day: SeriesDay) => number | null): number | null {
  const held = days.flatMap((day) => {
    const value = pick(day);
    return value === null || day.calls === 0 ? [] : [{ value, weight: day.calls }];
  });
  const weight = held.reduce((sum, one) => sum + one.weight, 0);
  return weight === 0 ? null : held.reduce((sum, one) => sum + one.value * one.weight, 0) / weight;
}

/** One stage of a turn over the window, and the vendor and model that took most of it. */
export interface Part {
  key: "hears" | "thinks" | "tools" | "speaks";
  name: string;
  seconds: number;
  /** Under the name: `deepgram · nova-3`, or how many times a tool ran. */
  by: string;
}

const STAGES = [
  { stage: "stt", key: "hears", name: "Hears" },
  { stage: "llm", key: "thinks", name: "Thinks" },
  { stage: "tts", key: "speaks", name: "Speaks" },
] as const;

/** The vendor and model that carried the stage's turns, and the stage's value across all of them, each weighted by its turns. */
export function stageOf(vendors: readonly SeriesVendor[], stage: string, tail: Tail): { seconds: number; vendor: string; model: string | null } | null {
  const rows = vendors.filter((one) => one.stage === stage && one[tail] !== null);
  const turns = rows.reduce((sum, one) => sum + one.turns, 0);
  // A turn whose report named no vendor counts in the stage's value but cannot be its name.
  const top = [...rows].filter((one) => one.vendor !== "").sort((a, b) => b.turns - a.turns)[0];
  if (turns === 0 || top === undefined) return null;
  return { seconds: rows.reduce((sum, one) => sum + (one[tail] ?? 0) * one.turns, 0) / turns, vendor: top.vendor, model: top.model };
}

/** The turn's parts in the order it happens; tools sit between thinking and speaking and are always the typical run, as no tail is counted for them. */
export function partsOf(vendors: readonly SeriesVendor[], tools: readonly ToolStat[], tail: Tail): Part[] {
  const stages = STAGES.flatMap((one) => {
    const at = stageOf(vendors, one.stage, tail);
    return at === null ? [] : [{ key: one.key, name: one.name, seconds: at.seconds, by: [at.vendor, at.model].filter((word) => word !== null).join(" · ") }];
  });
  const timed = tools.filter((tool) => tool.median_s !== null);
  const ran = timed.reduce((sum, tool) => sum + tool.ran, 0);
  const took = ran === 0 ? null : timed.reduce((sum, tool) => sum + (tool.median_s ?? 0) * tool.ran, 0) / ran;
  const among: Part[] = took === null ? [] : [{ key: "tools", name: "Tools", seconds: took, by: `${ran} ${ran === 1 ? "run" : "runs"}` }];
  const order = ["hears", "thinks", "tools", "speaks"];
  return [...stages, ...among].sort((a, b) => order.indexOf(a.key) - order.indexOf(b.key));
}
