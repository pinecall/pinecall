/** How long a turn takes and what a minute costs, off the agent's real calls: one card, drawn on Configure and on an app's overview. */

import type { ReactNode } from "react";

import type { Insights } from "../lib/insights";
import { WORLD } from "../lib/world";
import type { Report } from "./door";
import { Measures, type Slice } from "./measures";
import type { Measured } from "./stages";

export interface Measuring {
  total: number | null;
  calls: number;
  steps: readonly Slice[];
  rate: number | null;
  rateFrom: string | null;
  slices: readonly Slice[];
  measured: Readonly<Record<"hear" | "think" | "speak", Measured>>;
}

function medianOf(report: Report, name: string): number | null {
  return report.medians.find((one) => one.name === name)?.seconds ?? null;
}

/** What the agent's minutes cost in a window; none when nothing was spent, which prices nothing. */
function spendOf(counted: Insights | null, agent: string): Insights["agents"][number]["spend"] | null {
  const spend = counted?.agents.find((one) => one.slug === agent)?.spend ?? null;
  if (spend === null || spend.minutes === 0) return null;
  return spend.llm_usd + spend.stt_usd + spend.tts_usd + spend.phone_usd + spend.platform_usd === 0 ? null : spend;
}

/** The figures off the report and the insights. A production agent with no priced minutes yet is priced by its sandbox calls: the same vendors, and said so. */
export function measuringOf(agent: string, report: Report, counted: Insights | null, rehearsed: Insights | null): Measuring {
  const spentHere = spendOf(counted, agent);
  const spend = spentHere ?? (WORLD === "production" ? spendOf(rehearsed, agent) : null);
  const per = (usd: number | undefined): number | null => (spend === null || usd === undefined ? null : usd / spend.minutes);
  const costs = { hear: per(spend?.stt_usd), think: per(spend?.llm_usd), speak: per(spend?.tts_usd), phone: per(spend?.phone_usd), platform: per(spend?.platform_usd) };
  const eot = medianOf(report, "end_of_turn_delay");
  const transcription = medianOf(report, "transcription_delay");
  const hear = eot === null && transcription === null ? null : (eot ?? 0) + (transcription ?? 0);
  const think = medianOf(report, "llm_node_ttft");
  const speak = medianOf(report, "tts_node_ttfb");
  return {
    total: medianOf(report, "e2e_latency"),
    calls: report.calls,
    steps: [
      { name: "Transcriber", value: hear, tone: "accent" },
      { name: "Model", value: think, tone: "blue" },
      { name: "Voice", value: speak, tone: "pink" },
    ],
    rate: spend?.per_minute_usd ?? null,
    rateFrom: spend !== null && spentHere === null ? "from sandbox calls" : null,
    slices: [
      { name: "Transcriber", value: costs.hear, tone: "accent" },
      { name: "Model", value: costs.think, tone: "blue" },
      { name: "Voice", value: costs.speak, tone: "pink" },
      ...((costs.phone ?? 0) > 0 ? [{ name: "Phone", value: costs.phone, tone: "warn" as const }] : []),
      ...((costs.platform ?? 0) > 0 ? [{ name: "Platform", value: costs.platform, tone: "good" as const }] : []),
    ],
    measured: {
      hear: { latency: hear, cost: costs.hear },
      think: { latency: think, cost: costs.think },
      speak: { latency: speak, cost: costs.speak },
    },
  };
}

export function MeasuresCard({ report, measuring }: { report: Report; measuring: Measuring }): ReactNode {
  return (
    <section className="dash-card" aria-label="What it runs on">
      <Measures total={measuring.total} calls={measuring.calls} steps={measuring.steps} rate={measuring.rate} rateFrom={measuring.rateFrom} slices={measuring.slices} />
      {report.talks != null && (
        <p className="dash-quiet cfg-talks">
          On voice calls it runs on {report.talks.vendor}
          {report.talks.model === null ? "" : `/${report.talks.model}`}, which hears and speaks by itself.
        </p>
      )}
    </section>
  );
}
