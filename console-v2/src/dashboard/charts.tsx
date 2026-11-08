/** The dashboard's graphs, drawn by hand in the page's own palette: an area or bars over days with a reading under the pointer, and a split bar. */

import { useId, useState, type ReactNode } from "react";

export type Tone = "accent" | "good" | "blue" | "warn" | "pink" | "quiet";

const INK: Readonly<Record<Tone, string>> = {
  accent: "var(--accent)",
  good: "var(--good)",
  blue: "var(--blue)",
  warn: "var(--warn)",
  pink: "var(--pink)",
  quiet: "var(--quiet)",
};

export interface Point {
  label: string;
  /** Null: nothing to say that day, and the line breaks there. */
  value: number | null;
  /** What the reading adds under the value. */
  detail?: string;
}

interface At {
  x: number;
  y: number;
}

// Control points level with each end: a curve that never swings past the days it joins.
function curveThrough(run: readonly At[]): string {
  return run.reduce((path, one, at) => {
    const was = run[at - 1];
    if (was === undefined) return `M${one.x} ${one.y}`;
    const middle = (was.x + one.x) / 2;
    return `${path}C${middle} ${was.y} ${middle} ${one.y} ${one.x} ${one.y}`;
  }, "");
}

/** The stretches of days with something to draw, a null day between them. */
function runsOf(points: readonly (At | null)[]): At[][] {
  const runs: At[][] = [];
  let open: At[] = [];
  for (const point of points) {
    if (point === null) {
      if (open.length > 0) runs.push(open);
      open = [];
    } else open.push(point);
  }
  if (open.length > 0) runs.push(open);
  return runs;
}

/** The first of 1, 2, 4, 6, 8 × 10ⁿ at or over the highest value: its half is a round number too. */
function roomFor(highest: number): number {
  if (highest <= 0) return 1;
  const power = 10 ** Math.floor(Math.log10(highest));
  return ([1, 2, 4, 6, 8, 10].find((step) => step * power >= highest) ?? 10) * power;
}

export function DayChart({ kind, points, tone, said, top, atLeast = 0, nothing }: { kind: "area" | "bars"; points: readonly Point[]; tone: Tone; said: (value: number) => string; top?: number; atLeast?: number; nothing: string }): ReactNode {
  const [read, setRead] = useState<number | null>(null);
  const fill = useId();
  const values = points.map((point) => point.value ?? 0);
  const room = top ?? Math.max(atLeast, roomFor(Math.max(0, ...values)));
  const silent = points.every((point) => point.value === null || point.value === 0);
  const step = points.length > 14 ? 5 : 1;
  const heights = points.map((point) => (point.value === null ? null : (point.value / room) * 100));
  const placed = heights.map((height, at) => (height === null ? null : { x: ((at + 0.5) / points.length) * 100, y: 100 - height }));
  const runs = runsOf(placed);
  const reading = read === null ? undefined : points[read];
  const readAt = read === null ? 0 : ((read + 0.5) / points.length) * 100;
  return (
    <div className="dash-chart">
      <div className="dash-plot" onMouseLeave={() => setRead(null)}>
        {[1, 0.5, 0].map((share) => (
          <div key={share} className="dash-grid" style={{ bottom: `${share * 100}%` }}>
            {!silent && <span className="dash-grid-label">{said(room * share)}</span>}
          </div>
        ))}
        <div className="dash-draw">
          {kind === "area" && !silent && (
            <svg className="dash-svg" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
              <defs>
                <linearGradient id={fill} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={INK[tone]} stopOpacity="0.34" />
                  <stop offset="100%" stopColor={INK[tone]} stopOpacity="0" />
                </linearGradient>
              </defs>
              {runs.map((run) => {
                const first = run[0];
                const last = run[run.length - 1];
                if (first === undefined || last === undefined || run.length < 2) return null;
                const line = curveThrough(run);
                return (
                  <g key={first.x}>
                    <path d={`${line}L${last.x} 100L${first.x} 100Z`} fill={`url(#${fill})`} />
                    <path d={line} fill="none" stroke={INK[tone]} strokeWidth="2.25" vectorEffect="non-scaling-stroke" strokeLinecap="round" />
                  </g>
                );
              })}
            </svg>
          )}
          <div className="dash-columns">
            {points.map((point, at) => (
              <div key={point.label} className="dash-column" onMouseEnter={() => setRead(at)}>
                {kind === "bars" && <span className={read === at ? "dash-bar dash-bar-read" : "dash-bar"} style={{ height: `${heights[at] ?? 0}%`, background: INK[tone] }} />}
              </div>
            ))}
          </div>
          {kind === "area" &&
            !silent &&
            placed.map((one, at) => {
              const key = points[at]?.label ?? at;
              const alone = one !== null && placed[at - 1] == null && placed[at + 1] == null;
              if (one === null || (read !== at && !alone)) return null;
              return <span key={key} className={read === at ? "dash-point dash-point-read" : "dash-point"} style={{ left: `${one.x}%`, top: `${one.y}%`, borderColor: INK[tone] }} />;
            })}
          {reading !== undefined && kind === "area" && <span className="dash-rule" style={{ left: `${readAt}%` }} />}
          {reading !== undefined && (
            <div className="dash-reading" style={{ left: `${readAt}%`, transform: `translateX(${readAt > 70 ? "-100%" : readAt < 30 ? "0" : "-50%"})` }}>
              <span className="dash-reading-day">{reading.label}</span>
              <span className="dash-reading-value">{reading.value === null ? "—" : said(reading.value)}</span>
              {reading.detail !== undefined && <span className="dash-reading-day">{reading.detail}</span>}
            </div>
          )}
          {silent && <span className="dash-nothing">{nothing}</span>}
        </div>
      </div>
      <div className="dash-days" aria-hidden="true">
        {points.map((point, at) => (
          <span key={point.label} className="dash-day">
            {at % step === 0 ? point.label : ""}
          </span>
        ))}
      </div>
    </div>
  );
}

export interface Slice {
  name: string;
  count: number;
  tone: Tone;
}

/** How a whole divides: one bar in parts, and each part named with its count. */
export function SplitBar({ slices, nothing }: { slices: readonly Slice[]; nothing: string }): ReactNode {
  const total = slices.reduce((sum, slice) => sum + slice.count, 0);
  if (total === 0) return <p className="dash-empty">{nothing}</p>;
  return (
    <div className="dash-split">
      <div className="dash-split-bar" aria-hidden="true">
        {slices.map((slice) => (
          <span key={slice.name} style={{ flexGrow: slice.count, background: INK[slice.tone] }} />
        ))}
      </div>
      <ul className="dash-legend">
        {slices.map((slice) => (
          <li key={slice.name} className="dash-legend-row">
            <span className="dash-legend-dot" style={{ background: INK[slice.tone] }} aria-hidden="true" />
            <span className="dash-legend-name">{slice.name}</span>
            <span className="dash-legend-count">{slice.count}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
