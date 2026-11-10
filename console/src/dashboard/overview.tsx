/** The dashboard's measures: the window's headlines split in colour, what they are made of, and the graphs. */

import { useState, type ReactNode } from "react";

import { seconds } from "@pinecall/core/metrics";
import { count, dayLabel, money, percent } from "../lib/format";
import { callsOf, type Insights } from "../lib/insights";
import { spendSplit } from "../observability/fold";
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
      </div>
      <div className="dash-headline-bar" aria-hidden="true">
        {parts.some((part) => part.count > 0) ? parts.filter((part) => part.count > 0).map((part) => <span key={part.name} className={`dash-tone-${part.tone}`} style={{ flexGrow: part.count / Math.max(...parts.map((one) => one.count)) }} />) : <span className="dash-tone-none" style={{ flexGrow: 1 }} />}
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

function Figure({ name, value, note }: { name: string; value: string; note: string }): ReactNode {
  return (
    <div className="dash-figure">
      <span className="dash-dotted">{name}</span>
      <span className="dash-figure-value">{value}</span>
      <span className="dash-quiet dash-clip">{note}</span>
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
  const escalated = counted?.escalated ?? 0;
  const minutes = (counted?.agents ?? []).reduce((sum, one) => sum + one.spend.minutes, 0);
  const span = days === 1 ? "today" : `in ${days} days`;
  const blank = (said: () => string): string => (counted === null ? "—" : said());
  return (
    <div className="dash">
      <section className="dash-card" aria-label="The window's measures">
        <div className="dash-card-top">
          <span className="dash-eyebrow">{days === 1 ? "Today" : `The last ${days} days`}</span>
          {picker}
        </div>
        <div className="dash-headlines">
          <Headline
            label="Calls"
            value={blank(() => count(total))}
            unit={span}
            parts={[
              { name: "Phone", count: channels?.phone ?? 0, tone: "accent" },
              { name: "Web", count: channels?.web ?? 0, tone: "blue" },
              { name: "WhatsApp", count: channels?.whatsapp ?? 0, tone: "good" },
            ]}
          />
          <Headline
            label="Held by the judges"
            value={judged === 0 ? "—" : percent(passed / judged)}
            unit={`of ${count(judged)} judged`}
            parts={[
              { name: "Held", count: passed, tone: "good" },
              { name: "Broke", count: judged - passed, tone: "warn" },
            ]}
          />
          <Headline
            label="Resolved without a person"
            value={counted?.resolved_rate == null ? "—" : percent(counted.resolved_rate)}
            unit={`of ${count(total)} calls`}
            parts={[
              { name: "By the agent", count: Math.max(0, total - escalated), tone: "accent" },
              { name: "To a person", count: escalated, tone: "pink" },
            ]}
          />
          <Headline label="Spend" value={blank(() => money(counted?.spend_usd ?? 0))} unit={span} parts={spendSplit(counted?.agents ?? []).map((part) => ({ name: part.name, count: part.value, tone: part.tone, shown: money(part.value) }))} />
        </div>
        <div className="dash-figures">
          <Figure name="Against before" value={moved} note={days === 1 ? "Calls, against yesterday" : `Calls, against the ${days} days before`} />
          <Figure name="Time to answer" value={counted?.median_e2e_s == null ? "—" : seconds(counted.median_e2e_s)} note="Median, last word to first sound" />
          <Figure name="Avg length" value={counted?.mean_length_s == null ? "—" : `${Math.round(counted.mean_length_s)} s`} note={`${count(Math.round(minutes))} min on the line`} />
          <Figure name="Live now" value={String(live)} note={live === 0 ? "Nobody on the line" : live === 1 ? "Call going on" : "Calls going on"} />
          <Figure name="Per call" value={counted === null || total === 0 ? "—" : money(counted.spend_usd / total)} note={counted === null || minutes === 0 ? "Every vendor" : `${money(counted.spend_usd / minutes)} a minute`} />
          <Figure name="This month" value={blank(() => money(counted?.budget.spent_usd_month ?? 0))} note={budget === null ? "No budget set" : `Of a ${money(budget)} budget`} />
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
