/** The answer's time a day over the window picked: a dot on each day somebody called, straight between neighbours, dashed across the days nobody did, and the monitor's line across it when the org watches this number. */

import { useId, type ReactNode } from "react";

import { dayOf } from "../../lib/format";

const WIDTH = 700;
const HEIGHT = 150;
// A label every this many days once the window is long enough that every day would crowd.
const EVERY = 5;

function dayAt(day: string): string {
  return dayOf(Date.parse(`${day}T12:00:00Z`) / 1000);
}

export function AnswerChart({ days, values, says, line }: { days: readonly string[]; values: readonly (number | null)[]; says: (value: number) => string; line: { at: number; name: string } | null }): ReactNode {
  const fade = useId();
  const measured = values.flatMap((value, index) => (value === null ? [] : [{ index, value }]));
  if (measured.length === 0) return <p className="obs-quiet">Nothing in these days.</p>;
  const top = Math.max(...measured.map((one) => one.value), line?.at ?? 0) * 1.15 || 1;
  const span = Math.max(1, days.length - 1);
  // How far along the chart a day sits, from 0 to 1: a window of one day has it in the middle.
  const along = (index: number): number => (days.length === 1 ? 0.5 : index / span);
  const x = (index: number): number => along(index) * WIDTH;
  const y = (value: number): number => HEIGHT - (value / top) * HEIGHT;
  const at = (point: { index: number; value: number }): string => `${x(point.index)},${y(point.value)}`;
  // Solid between two days that follow each other; dashed over the days nobody called on.
  const joined: string[] = [];
  const bridged: string[] = [];
  const filled: string[] = [];
  measured.forEach((point, order) => {
    const next = measured[order + 1];
    if (next === undefined) return;
    if (next.index === point.index + 1) {
      joined.push(`M${at(point)} L${at(next)}`);
      filled.push(`M${x(point.index)},${HEIGHT} L${at(point)} L${at(next)} L${x(next.index)},${HEIGHT} Z`);
    } else bridged.push(`M${at(point)} L${at(next)}`);
  });
  // Labels on the days that carry one: every day of a short window, a regular few of a long one, and the last.
  const labelled = (index: number): boolean => days.length <= 7 || index % EVERY === 0 || index === days.length - 1;
  const place = (index: number): string => (days.length === 1 ? "obs-answer-day" : index === 0 ? "obs-answer-day obs-answer-day-first" : index === days.length - 1 ? "obs-answer-day obs-answer-day-last" : "obs-answer-day");

  return (
    <div className="obs-answer-chart">
      <div className="obs-answer-plot">
        <div className="obs-answer-grid" aria-hidden>
          <span />
          <span />
          <span />
          <span className="obs-answer-floor" />
        </div>
        <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} preserveAspectRatio="none" role="img" aria-label="Time to answer a day">
          <defs>
            <linearGradient id={fade} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" className="obs-answer-fade-top" />
              <stop offset="1" className="obs-answer-fade-foot" />
            </linearGradient>
          </defs>
          {filled.map((shape) => (
            <path key={shape} d={shape} fill={`url(#${fade})`} />
          ))}
          {bridged.map((shape) => (
            <path key={shape} d={shape} className="obs-answer-bridge" vectorEffect="non-scaling-stroke" />
          ))}
          {joined.map((shape) => (
            <path key={shape} d={shape} className="obs-answer-line" vectorEffect="non-scaling-stroke" />
          ))}
        </svg>
        {measured.map((point) => (
          <span key={point.index} className="obs-answer-dot" style={{ left: `${along(point.index) * 100}%`, top: `${(y(point.value) / HEIGHT) * 100}%` }} title={`${dayAt(days[point.index] ?? "")} · ${says(point.value)}`} />
        ))}
        {line !== null && (
          <>
            <div className="obs-answer-monitor" style={{ top: `${(y(line.at) / HEIGHT) * 100}%` }} />
            <span className="obs-answer-monitor-name" style={{ top: `${(y(line.at) / HEIGHT) * 100}%` }}>
              monitor · {line.name} {says(line.at)}
            </span>
          </>
        )}
      </div>
      <div className="obs-answer-days">
        {days.map((day, index) =>
          labelled(index) ? (
            <span key={day} className={place(index)} style={{ left: `${along(index) * 100}%` }}>
              {dayAt(day)}
            </span>
          ) : null,
        )}
      </div>
    </div>
  );
}
