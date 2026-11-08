/** The dashboard's measures: the window's headlines split in colour, what they are made of, and the graphs. */

import { useState, type ReactNode } from "react";

import { seconds } from "@pinecall/core/metrics";
import { count, dayLabel, money, percent } from "../lib/format";
import { callsOf, type Insights } from "../lib/insights";
import { DayChart, SplitBar, type Point, type Slice, type Tone } from "./charts";

const SPLIT_TONES: readonly Tone[] = ["accent", "blue", "good", "warn", "pink"];

type Metric = "calls" | "held" | "spend";
const METRICS: readonly { value: Metric; name: string }[] = [
  { value: "calls", name: "Calls" },
  { value: "held", name: "Held" },
  { value: "spend", name: "Spend" },
];

function endingsOf(counted: Insights | null): Slice[] {
  const endings = counted?.endings ?? [];
  const named = endings.slice(0, SPLIT_TONES.length).map((one, at) => ({ name: one.reason.replace(/_/g, " "), count: one.count, tone: SPLIT_TONES[at] ?? "quiet" }));
  const rest = endings.slice(SPLIT_TONES.length).reduce((sum, one) => sum + one.count, 0);
  return rest === 0 ? named : [...named, { name: "other", count: rest, tone: "quiet" }];
}

export function Headline({ label, value, unit, parts }: { label: string; value: string; unit: string; parts: readonly (Slice & { shown?: string })[] }): ReactNode {
  return (
    <div className="dash-headline">
      <span className="dash-dotted">{label}</span>
      <div className="dash-headline-line">
        <span className="dash-headline-value">{value}</span>
        <span className="dash-quiet">{unit}</span>
        <div className="dash-headline-bar" aria-hidden="true">
          {parts.some((part) => part.count > 0) ? parts.filter((part) => part.count > 0).map((part) => <span key={part.name} className={`dash-tone-${part.tone}`} style={{ flexGrow: part.count / Math.max(...parts.map((one) => one.count)) }} />) : <span className="dash-tone-none" style={{ flexGrow: 1 }} />}
        </div>
      </div>
      <div className="dash-keys">
        {parts.map((part) => (
          <span key={part.name} className="dash-key">
            <span className={`dash-key-dot dash-tone-${part.tone}`} aria-hidden="true" />
            {part.name} <b>{part.shown ?? part.count}</b>
          </span>
        ))}
      </div>
    </div>
  );
}

export function Part({ title, value, under, facts }: { title: string; value: string; under: string; facts: readonly { name: string; value: string }[] }): ReactNode {
  return (
    <div className="dash-part">
      <span className="dash-eyebrow">{title}</span>
      <span className="dash-part-value">{value}</span>
      <span className="dash-quiet">{under}</span>
      <dl className="dash-facts">
        {facts.map((fact) => (
          <div key={fact.name}>
            <dt className="dash-dotted">{fact.name}</dt>
            <dd>{fact.value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

export function Overview({ counted, moved, days, live, picker }: { counted: Insights | null; moved: string; days: number; live: number; picker: ReactNode }): ReactNode {
  const [metric, setMetric] = useState<Metric>("calls");
  const series = counted?.series ?? [];
  const calls: Point[] = series.map((day) => ({ label: dayLabel(day.day), value: callsOf(day), detail: `${day.phone} phone, ${day.web} web, ${day.whatsapp} WhatsApp` }));
  const held: Point[] = series.map((day) => ({ label: dayLabel(day.day), value: day.judged === 0 ? null : day.passed / day.judged, detail: `${day.passed} of ${day.judged} calls` }));
  const spent: Point[] = series.map((day) => ({ label: dayLabel(day.day), value: day.spend_usd }));

  const total = counted?.conversations.now ?? 0;
  const judged = counted?.judged ?? 0;
  const passed = counted?.passed ?? 0;
  const channels = counted?.channels;
  const budget = counted?.budget.limit_usd ?? null;
  return (
    <div className="dash">
      <section className="dash-card" aria-label="The window's measures">
        <div className="dash-headlines">
          <Headline
            label="Calls"
            value={counted === null ? "—" : count(total)}
            unit={days === 1 ? "today" : `in ${days} days`}
            parts={[
              { name: "Phone", count: channels?.phone ?? 0, tone: "accent" },
              { name: "Web", count: channels?.web ?? 0, tone: "blue" },
              { name: "WhatsApp", count: channels?.whatsapp ?? 0, tone: "good" },
            ]}
          />
          <Headline
            label="Held by the judges"
            value={judged === 0 ? "—" : percent(passed / judged)}
            unit={`of ${judged} judged`}
            parts={[
              { name: "Held", count: passed, tone: "good" },
              { name: "Broke", count: judged - passed, tone: "warn" },
            ]}
          />
          {picker}
        </div>
        <div className="dash-parts">
          <Part
            title="Conversations"
            value={counted?.resolved_rate == null ? "—" : percent(counted.resolved_rate)}
            under="Resolved without a person"
            facts={[
              { name: "Against before", value: moved },
              { name: "Avg length", value: counted?.mean_length_s == null ? "—" : `${Math.round(counted.mean_length_s)} s` },
              { name: "Live now", value: String(live) },
            ]}
          />
          <Part
            title="Answers"
            value={counted?.median_e2e_s == null ? "—" : seconds(counted.median_e2e_s)}
            under="Median time to answer"
            facts={[
              { name: "Judged", value: counted === null ? "—" : count(judged) },
              { name: "Held", value: counted === null ? "—" : count(passed) },
              { name: "To a person", value: counted === null ? "—" : count(counted.escalated) },
            ]}
          />
          <Part
            title="Spend"
            value={counted === null ? "—" : money(counted.spend_usd)}
            under={days === 1 ? "Today" : `In ${days} days`}
            facts={[
              { name: "Per call", value: counted === null || total === 0 ? "—" : money(counted.spend_usd / total) },
              { name: "This month", value: counted === null ? "—" : money(counted.budget.spent_usd_month) },
              { name: "Budget", value: budget === null ? "None" : money(budget) },
            ]}
          />
        </div>
      </section>

      <div className="dash-wide">
        <section className="dash-card" aria-label="A day at a time">
          <div className="dash-card-top">
            <span className="dash-eyebrow">A day at a time</span>
            <div className="dash-switch" role="group" aria-label="What is drawn">
              {METRICS.map((one) => (
                <button key={one.value} type="button" aria-pressed={one.value === metric} className={one.value === metric ? "dash-switch-on" : ""} onClick={() => setMetric(one.value)}>
                  {one.name}
                </button>
              ))}
            </div>
          </div>
          {metric === "calls" && <DayChart kind="area" points={calls} tone="accent" atLeast={2} said={(value) => count(Math.round(value))} nothing="No calls in these days." />}
          {metric === "held" && <DayChart kind="area" points={held} tone="good" top={1} said={percent} nothing="Nothing judged in these days." />}
          {metric === "spend" && <DayChart kind="bars" points={spent} tone="blue" said={money} nothing="No spend in these days." />}
        </section>
        <section className="dash-card" aria-label="How calls end">
          <div className="dash-card-top">
            <span className="dash-eyebrow">How calls end</span>
          </div>
          <SplitBar slices={endingsOf(counted)} nothing="No call has ended in these days." />
        </section>
      </div>
    </div>
  );
}
