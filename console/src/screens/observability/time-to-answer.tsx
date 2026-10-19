/** Time to answer: how long a caller waits for the agent's first sound, how it moved, where the time goes, and the day-by-day line. */

import { useMemo, useState, type ReactNode } from "react";

import type { Series, SeriesDay } from "../../lib/series";
import type { ToolStat } from "../../lib/tools";
import { Card } from "../../ui";
import type { Monitor } from "../monitors";
import { AnswerChart } from "./answer-chart";
import { across, partsOf, type Tail } from "./answer";

const TAILS: readonly { tail: Tail; label: string }[] = [
  { tail: "median_s", label: "Typical (p50)" },
  { tail: "p95_s", label: "Slow calls (p95)" },
];

const seconds = (value: number): string => (value < 1 ? `${Math.round(value * 1000)} ms` : value >= 10 ? `${Math.round(value)} s` : `${value.toFixed(2)} s`);

/** The number a day carries for each tail, and the monitor that watches it where there is one. */
const DAILY: Record<Tail, { pick: (day: SeriesDay) => number | null; monitor: string | null; name: string }> = {
  median_s: { pick: (day) => day.e2e_median_s, monitor: "e2e_median_s", name: "p50 over" },
  p95_s: { pick: (day) => day.e2e_p95_s, monitor: null, name: "p95 over" },
};

export function TimeToAnswer({ now, before, tools, monitors, agent, range }: { now: Series | null; before: Series | null; tools: readonly ToolStat[]; monitors: readonly Monitor[]; agent: string; range: number }): ReactNode {
  const [tail, setTail] = useState<Tail>("median_s");
  const rows = now?.series ?? [];
  const daily = DAILY[tail];
  const value = useMemo(() => across(rows, daily.pick), [rows, daily]);
  const was = useMemo(() => across(before?.series ?? [], daily.pick), [before, daily]);
  const moved = value === null || was === null ? null : Math.round((value - was) * 10) / 10;
  const parts = useMemo(() => partsOf(now?.vendors ?? [], tools, tail), [now, tools, tail]);
  const total = parts.reduce((sum, part) => sum + part.seconds, 0);
  // The line the org drew for this number: the one for every agent, or for the agent in view.
  const watched = monitors.find((one) => one.metric === daily.monitor && one.above && (one.agent === null || one.agent === agent));

  return (
    <Card pad>
      <div className="obs-answer">
        <div className="obs-answer-head">
          <div className="obs-answer-words">
            <span className="obs-answer-label">Time to answer</span>
            <div className="obs-answer-now">
              <span className="obs-answer-value">{value === null ? "—" : seconds(value)}</span>
              <span className="obs-answer-delta">
                {moved === null ? `the last ${range} days` : Math.abs(moved) < 0.1 ? `steady against the ${range} days before` : `${Math.abs(moved).toFixed(1)} s ${moved < 0 ? "faster" : "slower"} than the ${range} days before`}
              </span>
            </div>
            <span className="obs-answer-what">From when the caller stops talking to the agent's first sound.</span>
          </div>
          <span className="obs-tails" role="group" aria-label="Which turns">
            {TAILS.map((one) => (
              <button key={one.tail} type="button" className={tail === one.tail ? "obs-tail obs-tail-on" : "obs-tail"} onClick={() => setTail(one.tail)}>
                {one.label}
              </button>
            ))}
          </span>
        </div>

        {parts.length > 0 && (
          <div className="obs-split">
            <span className="obs-answer-label">Where the time goes</span>
            <div className="obs-split-bar" role="img" aria-label="The time to answer, by stage">
              {parts.map((part) => (
                <span key={part.key} className={`obs-split-part obs-part-${part.key}`} style={{ width: `${(part.seconds / total) * 100}%` }} title={`${part.name} ${seconds(part.seconds)}`} />
              ))}
            </div>
            <div className="obs-split-legend">
              {parts.map((part) => (
                <div key={part.key} className="obs-split-one">
                  <span className={`obs-split-key obs-part-${part.key}`} aria-hidden />
                  <span className="obs-split-words">
                    <span>
                      <span className="obs-split-name">{part.name}</span> <span className="obs-split-took">{seconds(part.seconds)}</span>
                    </span>
                    {part.by !== "" && <span className="obs-split-by">{part.by}</span>}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        <AnswerChart days={rows.map((day) => day.day)} values={rows.map(daily.pick)} says={seconds} line={watched === undefined ? null : { at: watched.threshold, name: daily.name }} />
      </div>
    </Card>
  );
}
