/** The share of judged calls that held, a day at a time, as one line over the window the gateway counted; a day nobody judged is a gap, not a zero. */

import { useState, type ReactNode } from "react";

import { dayOf } from "../../lib/format";
import type { InsightsDay } from "../../lib/insights";

const WIDTH = 640;
const HEIGHT = 170;
const LEFT = 38;
const BOTTOM = 22;
const TOP = 10;
const PLOT = HEIGHT - BOTTOM - TOP;

function dayAt(day: string): string {
  return dayOf(Date.parse(`${day}T12:00:00Z`) / 1000);
}

export function HeldByDay({ series }: { series: readonly InsightsDay[] }): ReactNode {
  const [on, setOn] = useState<number | null>(null);
  const shares = series.map((day) => (day.judged === 0 ? null : day.passed / day.judged));
  const known = shares.filter((share): share is number => share !== null);
  if (known.length === 0) return <p className="qly-quiet">No call was judged in these days.</p>;
  // The floor is the lowest tenth any day reached, so a fall from 98% to 91% is a fall to the eye.
  const floor = Math.max(0, Math.floor(Math.min(...known) * 10) / 10 - 0.1);
  const step = (WIDTH - LEFT) / Math.max(1, series.length - 1);
  const x = (index: number): number => LEFT + index * step;
  const y = (share: number): number => TOP + PLOT - ((share - floor) / (1 - floor)) * PLOT;
  // One path per run of judged days: a day nobody judged breaks the line instead of dragging it to zero.
  const runs: string[] = [];
  let run: string[] = [];
  shares.forEach((share, index) => {
    if (share === null) {
      if (run.length > 0) runs.push(run.join(" "));
      run = [];
      return;
    }
    run.push(`${run.length === 0 ? "M" : "L"}${x(index)} ${y(share)}`);
  });
  if (run.length > 0) runs.push(run.join(" "));
  // A day nobody judged is bridged by a dotted stroke between the judged days either side.
  const judgedDays = shares.map((share, index) => ({ share, index })).filter((one): one is { share: number; index: number } => one.share !== null);
  const bridges = judgedDays.slice(1).flatMap((here, at) => {
    const before = judgedDays[at];
    return before === undefined || here.index - before.index === 1 ? [] : [`M${x(before.index)} ${y(before.share)} L${x(here.index)} ${y(here.share)}`];
  });
  const last = shares.reduce<number | null>((found, share, index) => (share === null ? found : index), null);
  const hovered = on === null ? undefined : series[on];
  const hoveredShare = on === null ? null : (shares[on] ?? null);
  const ticks = [floor, (floor + 1) / 2, 1];

  return (
    <div className="qly-chart">
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label="Share of judged calls that held, a day at a time" onMouseLeave={() => setOn(null)}>
        {ticks.map((tick) => (
          <g key={tick}>
            <line x1={LEFT} x2={WIDTH} y1={y(tick)} y2={y(tick)} className="qly-grid" />
            <text x={LEFT - 8} y={y(tick) + 3.5} className="qly-tick" textAnchor="end">
              {Math.round(tick * 100)}%
            </text>
          </g>
        ))}
        {bridges.map((path) => (
          <path key={path} d={path} className="qly-bridge" />
        ))}
        {runs.map((path) => (
          <path key={path} d={path} className="qly-line" />
        ))}
        {judgedDays.map((one) => (
          <circle key={one.index} cx={x(one.index)} cy={y(one.share)} r={2.5} className="qly-dot" />
        ))}
        {last !== null && shares[last] !== null && <circle cx={x(last)} cy={y(shares[last] ?? 1)} r={3.5} className="qly-dot" />}
        {on !== null && <line x1={x(on)} x2={x(on)} y1={TOP} y2={TOP + PLOT} className="qly-cross" />}
        {on !== null && hoveredShare !== null && <circle cx={x(on)} cy={y(hoveredShare)} r={4.5} className="qly-dot" />}
        {series.map((day, index) => (
          <g key={day.day} onMouseEnter={() => setOn(index)}>
            <rect x={x(index) - step / 2} y={TOP} width={step} height={PLOT} className="qly-hit" />
            {(index === 0 || index === series.length - 1 || index === Math.floor((series.length - 1) / 2)) && (
              <text x={x(index)} y={HEIGHT - 6} className="qly-tick" textAnchor={index === 0 ? "start" : index === series.length - 1 ? "end" : "middle"}>
                {dayAt(day.day)}
              </text>
            )}
          </g>
        ))}
      </svg>
      {hovered !== undefined && on !== null && (
        <div className="qly-tip" style={{ left: `${(x(on) / WIDTH) * 100}%` }}>
          <div className="qly-tip-head">{dayAt(hovered.day)}</div>
          <div className="qly-tip-row">
            {hovered.judged === 0 ? "Nothing judged" : `${Math.round((hovered.passed / hovered.judged) * 100)}% held · ${hovered.passed} of ${hovered.judged}`}
          </div>
        </div>
      )}
    </div>
  );
}
