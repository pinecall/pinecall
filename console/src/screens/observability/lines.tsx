/** A line chart over the window's days: one line per series, a gap where a day has nothing, a hover that says the day. */

import { useState, type ReactNode } from "react";

import { dayOf } from "../../lib/format";

const WIDTH = 640;
const HEIGHT = 170;
const LEFT = 44;
const BOTTOM = 22;
const TOP = 10;
const PLOT = HEIGHT - BOTTOM - TOP;

/** One line: its name, its value per day (null for none), and how a value is said. */
export interface Line {
  name: string;
  values: (number | null)[];
  tone: 1 | 2 | 3 | 4;
}

function dayAt(day: string): string {
  return dayOf(Date.parse(`${day}T12:00:00Z`) / 1000);
}

/** `says` turns a value into words for the axis and the tip ("1.2 s", "96%"). */
export function Lines({ days, lines, says, label, ceiling }: { days: string[]; lines: Line[]; says: (value: number) => string; label: string; ceiling?: number | undefined }): ReactNode {
  const [on, setOn] = useState<number | null>(null);
  const known = lines.flatMap((line) => line.values.filter((value): value is number => value !== null));
  if (known.length === 0) return <p className="obs-quiet">Nothing in these days.</p>;
  // A share tops out at 100%; anything else gets headroom over its highest day.
  const top = ceiling ?? (Math.max(...known) * 1.15 || 1);
  const step = (WIDTH - LEFT) / Math.max(1, days.length - 1);
  const x = (index: number): number => LEFT + index * step;
  const y = (value: number): number => TOP + PLOT - (value / top) * PLOT;
  const ticks = [0, top / 2, top];
  const paths = lines.map((line) => {
    const runs: string[] = [];
    let run: string[] = [];
    line.values.forEach((value, index) => {
      if (value === null) {
        if (run.length > 0) runs.push(run.join(" "));
        run = [];
        return;
      }
      run.push(`${run.length === 0 ? "M" : "L"}${x(index)} ${y(value)}`);
    });
    if (run.length > 0) runs.push(run.join(" "));
    return runs;
  });
  // A day with nothing is bridged by a dotted stroke between the days either side that have.
  const bridges = lines.map((line) => {
    const known = line.values.map((value, index) => ({ value, index })).filter((one): one is { value: number; index: number } => one.value !== null);
    return known.slice(1).flatMap((here, at) => {
      const before = known[at];
      return before === undefined || here.index - before.index === 1 ? [] : [`M${x(before.index)} ${y(before.value)} L${x(here.index)} ${y(here.value)}`];
    });
  });
  const dots = lines.map((line) => line.values.map((value, index) => ({ value, index })).filter((one): one is { value: number; index: number } => one.value !== null));
  const hovered = on === null ? null : on;
  return (
    <div className="obs-chart">
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label={label} onMouseLeave={() => setOn(null)}>
        {ticks.map((tick) => (
          <g key={tick}>
            <line x1={LEFT} x2={WIDTH} y1={y(tick)} y2={y(tick)} className="obs-rule" />
            <text x={LEFT - 8} y={y(tick) + 3.5} className="obs-tick" textAnchor="end">
              {says(tick)}
            </text>
          </g>
        ))}
        {bridges.map((runs, at) => runs.map((path) => <path key={`${lines[at]?.name}-bridge-${path}`} d={path} className={`obs-bridge obs-line-${lines[at]?.tone ?? 1}`} />))}
        {paths.map((runs, at) => runs.map((path) => <path key={`${lines[at]?.name}-${path}`} d={path} className={`obs-line obs-line-${lines[at]?.tone ?? 1}`} />))}
        {dots.map((known, at) => known.map((one) => <circle key={`${lines[at]?.name}-${one.index}`} cx={x(one.index)} cy={y(one.value)} r={2.5} className={`obs-dot obs-dot-${lines[at]?.tone ?? 1}`} />))}
        {hovered !== null && <line x1={x(hovered)} x2={x(hovered)} y1={TOP} y2={TOP + PLOT} className="obs-cross" />}
        {hovered !== null &&
          lines.map((line) => {
            const value = line.values[hovered];
            return value === null || value === undefined ? null : <circle key={line.name} cx={x(hovered)} cy={y(value)} r={4} className={`obs-dot obs-dot-${line.tone}`} />;
          })}
        {days.map((day, index) => (
          <g key={day} onMouseEnter={() => setOn(index)}>
            <rect x={x(index) - step / 2} y={TOP} width={step} height={PLOT} className="obs-hit" />
            {(index === 0 || index === days.length - 1 || index === Math.floor((days.length - 1) / 2)) && (
              <text x={x(index)} y={HEIGHT - 6} className="obs-tick" textAnchor={index === 0 ? "start" : index === days.length - 1 ? "end" : "middle"}>
                {dayAt(day)}
              </text>
            )}
          </g>
        ))}
      </svg>
      <div className="obs-legend">
        {lines.map((line) => (
          <span key={line.name} className={`obs-key obs-key-${line.tone}`}>
            {line.name}
          </span>
        ))}
      </div>
      {hovered !== null && days[hovered] !== undefined && (
        <div className="obs-tip" style={{ left: `${(x(hovered) / WIDTH) * 100}%` }}>
          <div className="obs-tip-head">{dayAt(days[hovered] ?? "")}</div>
          {lines.map((line) => {
            const value = line.values[hovered];
            return (
              <div key={line.name} className="obs-tip-row">
                {line.name} · {value === null || value === undefined ? "—" : says(value)}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
