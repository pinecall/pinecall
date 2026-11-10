/** The window a day at a time: what was spent and on what, each stage's wait, the judges, how calls ended, how long they ran, the tools. */

import { useMemo, type ReactNode } from "react";

import { Ring } from "../configure/measures";
import { DayChart, type Tone } from "../dashboard/charts";
import { count, dayLabel, money, percent } from "../lib/format";
import type { Insights } from "../lib/insights";
import { LinesChart, StackChart, type Line } from "./chart";
import type { SeriesDay } from "./door";
import { dayStage, endingsOf, failuresOf, lengthSaid, spendSplit, took, VENDOR_STAGES, type Tail } from "./fold";

const JUDGE_TONES: readonly Tone[] = ["accent", "blue", "good", "pink"];

function ChartCard({ title, note, children }: { title: string; note: string; children: ReactNode }): ReactNode {
  return (
    <section className="dash-card ob-card" aria-label={title}>
      <div className="dash-card-top ob-card-top">
        <span className="dash-eyebrow">{title}</span>
        <span className="dash-quiet ob-clip">{note}</span>
      </div>
      {children}
    </section>
  );
}

/** What the window cost, what the money went to, and the spend a day. `agents` is null until the split is read. */
export function SpendCard({ rows, agents, said }: { rows: readonly SeriesDay[]; agents: Insights["agents"] | null; said: string }): ReactNode {
  const total = rows.reduce((sum, day) => sum + day.spend_usd, 0);
  const slices = spendSplit(agents ?? []).map((one) => ({ ...one, shown: money(one.value) }));
  const split = slices.reduce((sum, one) => sum + one.value, 0);
  return (
    <section className="dash-card ob-card ob-spend" aria-label="Spend">
      <div className="ob-spend-ring">
        <Ring title="Spend" figure={money(total)} note={split === 0 ? `in ${said}, not split by stage yet` : `in ${said}`} slices={slices} />
      </div>
      <div className="ob-spend-days">
        <span className="dash-eyebrow">A day at a time</span>
        <DayChart kind="bars" tone="blue" points={rows.map((day) => ({ label: dayLabel(day.day), value: day.spend_usd, detail: `${count(day.calls)} calls` }))} said={money} nothing="Nothing was spent in these days." />
      </div>
    </section>
  );
}

export function DayByDay({ rows, said }: { rows: readonly SeriesDay[]; said: string }): ReactNode {
  const days = useMemo(() => rows.map((day) => day.day), [rows]);
  const stagesAt = (tail: Tail): Line[] => VENDOR_STAGES.map((one) => ({ name: one.name, tone: one.tone, values: rows.map((day) => dayStage(day, one.stage)?.[tail] ?? null) }));
  const judges: Line[] = useMemo(() => {
    const names = [...new Set(rows.flatMap((day) => day.judges.map((judge) => judge.name)))].sort();
    return names.slice(0, JUDGE_TONES.length).map((name, at) => ({
      name,
      tone: JUDGE_TONES[at] ?? "quiet",
      values: rows.map((day) => {
        const judge = day.judges.find((one) => one.name === name);
        return judge === undefined || judge.judged === 0 ? null : judge.held / judge.judged;
      }),
    }));
  }, [rows]);
  const endings = useMemo(() => endingsOf(rows), [rows]);
  const failures = useMemo(() => failuresOf(rows), [rows]);
  // A day nobody called is a gap, not a zero.
  const onCallDays = (pick: (day: SeriesDay) => number): (number | null)[] => rows.map((day) => (day.calls === 0 ? null : pick(day)));
  const whole = (value: number): string => count(Math.round(value));

  return (
    <div className="ob-grid">
      <ChartCard title="Each stage, typical" note="The wait each stage adds to a turn">
        <LinesChart days={days} lines={stagesAt("median_s")} said={took} nothing="No turn was timed in these days." />
      </ChartCard>
      <ChartCard title="Each stage, slowest" note="The slowest turn in twenty">
        <LinesChart days={days} lines={stagesAt("p95_s")} said={took} nothing="No turn was timed in these days." />
      </ChartCard>
      <ChartCard title="Held, by judge" note="The share of its verdicts each judge held">
        <LinesChart days={days} lines={judges} said={percent} top={1} nothing="No call was judged in these days." />
      </ChartCard>
      <ChartCard title="Judges that said no" note="The one that said it most first">
        {failures.length === 0 ? (
          <p className="dash-empty">No judge said no in {said}.</p>
        ) : (
          <div className="dash-rows">
            {failures.map((one) => (
              <div key={one.name} className="ob-row dash-row">
                <span className="ob-row-main">
                  <span className="ob-mono ob-clip">{one.name}</span>
                </span>
                <span className="ob-num ob-num-runs dash-quiet">
                  {one.broken} of {one.judged}
                </span>
                <span className="ob-num dash-mood-warn">{percent(one.broken / one.judged)}</span>
              </div>
            ))}
          </div>
        )}
      </ChartCard>
      <ChartCard title="How calls ended" note="By reason">
        <StackChart stacks={endings.stacks} keys={endings.keys} nothing="No call has ended in these days." />
      </ChartCard>
      <ChartCard title="Calls" note="And how many a person took over">
        <LinesChart
          days={days}
          lines={[
            { name: "Calls", tone: "accent", values: onCallDays((day) => day.calls) },
            { name: "A person took over", tone: "warn", values: onCallDays((day) => day.escalated) },
          ]}
          said={whole}
          nothing="No calls in these days."
        />
      </ChartCard>
      <ChartCard title="Call length" note="The average of the calls that ended">
        <LinesChart days={days} lines={[{ name: "Average length", tone: "accent", values: rows.map((day) => day.mean_length_s) }]} said={lengthSaid} nothing="No call has ended in these days." />
      </ChartCard>
      <ChartCard title="Tools" note="Runs, and the ones that answered an error">
        <LinesChart
          days={days}
          lines={[
            { name: "Ran", tone: "blue", values: onCallDays((day) => day.tools_ran) },
            { name: "Failed", tone: "warn", values: onCallDays((day) => day.tools_failed) },
          ]}
          said={whole}
          nothing="No tool ran in these days."
        />
      </ChartCard>
    </div>
  );
}
