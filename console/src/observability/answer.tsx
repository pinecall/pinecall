/** Time to answer: how long a caller waits for the agent's first sound, the road of stages that wait is made of, and the wait a day at a time. */

import { useMemo, useState, type ReactNode } from "react";

import { percent } from "../lib/format";
import { LinesChart } from "./chart";
import { lineOver, type Monitor, type Series, type SeriesDay, type ToolStat } from "./door";
import { across, partsOf, took, type Tail } from "./fold";

const TAILS: readonly { tail: Tail; label: string; name: string; pick: (day: SeriesDay) => number | null; monitor: string | null }[] = [
  { tail: "median_s", label: "Typical", name: "The typical turn", pick: (day) => day.e2e_median_s, monitor: "e2e_median_s" },
  { tail: "p95_s", label: "Slowest", name: "The slowest turn in twenty", pick: (day) => day.e2e_p95_s, monitor: null },
];

export function TimeToAnswer({ series, tools, monitors, agent }: { series: Series; tools: readonly ToolStat[]; monitors: readonly Monitor[]; agent: string }): ReactNode {
  const [tail, setTail] = useState<Tail>("median_s");
  const chosen = TAILS.find((one) => one.tail === tail) ?? TAILS[0];
  const rows = series.series;
  const value = useMemo(() => (chosen === undefined ? null : across(rows, chosen.pick)), [rows, chosen]);
  const parts = useMemo(() => partsOf(series.vendors, tools, tail), [series, tools, tail]);
  const whole = parts.reduce((sum, part) => sum + part.seconds, 0);
  if (chosen === undefined) return null;
  const watched = lineOver(monitors, chosen.monitor, agent);

  return (
    <section className="dash-card ob-card" aria-label="Time to answer">
      <div className="ob-answer-top">
        <div className="ob-answer-words">
          <span className="dash-eyebrow">Time to answer</span>
          <p className="ob-answer-figure">
            {value === null ? "—" : took(value)}
            <span className="dash-quiet">{chosen.name.toLowerCase()}, from the caller's last word to the agent's first sound</span>
          </p>
        </div>
        <div className="dash-switch" role="group" aria-label="Which turns">
          {TAILS.map((one) => (
            <button key={one.tail} type="button" aria-pressed={one.tail === tail} className={one.tail === tail ? "dash-switch-on" : ""} onClick={() => setTail(one.tail)}>
              {one.label}
            </button>
          ))}
        </div>
      </div>

      {parts.length > 0 && (
        <div className="ob-road" role="img" aria-label={`Where the wait goes: ${parts.map((part) => `${part.name} ${took(part.seconds)}`).join(", ")}`}>
          <div className="ob-road-ends dash-quiet">
            <span>Caller stops</span>
            <span>Agent speaks</span>
          </div>
          <div className="ob-road-bar" aria-hidden="true">
            {parts.map((part) => (
              <span key={part.stage} className={`ob-tone-${part.tone}`} style={{ flexGrow: part.seconds }} />
            ))}
          </div>
          <div className="ob-steps">
            {parts.map((part) => (
              <div key={part.stage} className={`ob-step ob-tone-${part.tone}`}>
                <span className="ob-step-name">
                  <span className="ob-swatch" aria-hidden="true" />
                  {part.name}
                  <span className="ob-step-share dash-quiet">{whole === 0 ? "" : percent(part.seconds / whole)}</span>
                </span>
                <span className="ob-step-took">{took(part.seconds)}</span>
                <span className="dash-quiet ob-break">{part.by}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <LinesChart
        days={rows.map((day) => day.day)}
        lines={[{ name: chosen.name, tone: "accent", values: rows.map(chosen.pick) }]}
        said={took}
        mark={watched === undefined ? undefined : { at: watched.threshold, name: "A monitor watches" }}
        nothing="No turn was timed in these days."
      />
    </section>
  );
}
