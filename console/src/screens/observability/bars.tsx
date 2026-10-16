/** Stacked bars over the window's days: one bar a day, each key its own fill, a hover that says the day's numbers. */

import { useState, type ReactNode } from "react";

import { dayOf } from "../../lib/format";

const WIDTH = 640;
const HEIGHT = 170;
const LEFT = 30;
const BOTTOM = 22;
const TOP = 8;
const PLOT = HEIGHT - BOTTOM - TOP;

/** One day's stack: the day, and a count per key. */
export interface Stack {
  day: string;
  counts: Record<string, number>;
}

function ticksFor(most: number): number[] {
  const step = Math.max(1, Math.ceil(most / 3));
  return [0, step, step * 2, step * 3];
}

function dayAt(day: string): string {
  return dayOf(Date.parse(`${day}T12:00:00Z`) / 1000);
}

const total = (stack: Stack): number => Object.values(stack.counts).reduce((sum, count) => sum + count, 0);

/** `keys` are drawn bottom up in the order given, each in the tone of its index. */
export function Bars({ stacks, keys, label, said }: { stacks: Stack[]; keys: string[]; label: string; said: (key: string) => string }): ReactNode {
  const [on, setOn] = useState<number | null>(null);
  if (stacks.every((stack) => total(stack) === 0)) return <p className="obs-quiet">Nothing in these days.</p>;
  const ticks = ticksFor(Math.max(1, ...stacks.map(total)));
  const top = ticks[ticks.length - 1] ?? 1;
  const slot = (WIDTH - LEFT) / stacks.length;
  const bar = Math.min(26, slot * 0.62);
  const y = (value: number): number => TOP + PLOT - (value / top) * PLOT;
  const hovered = on === null ? undefined : stacks[on];
  return (
    <div className="obs-chart">
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label={label} onMouseLeave={() => setOn(null)}>
        {ticks.map((tick) => (
          <g key={tick}>
            <line x1={LEFT} x2={WIDTH} y1={y(tick)} y2={y(tick)} className="obs-rule" />
            <text x={LEFT - 8} y={y(tick) + 3.5} className="obs-tick" textAnchor="end">
              {tick}
            </text>
          </g>
        ))}
        {stacks.map((stack, index) => {
          const x = LEFT + index * slot + (slot - bar) / 2;
          let base = 0;
          return (
            <g key={stack.day} onMouseEnter={() => setOn(index)}>
              <rect x={LEFT + index * slot} y={TOP} width={slot} height={PLOT} className="obs-hit" />
              {keys.map((key, at) => {
                const value = stack.counts[key] ?? 0;
                if (value === 0) return null;
                const from = y(base);
                base += value;
                const height = Math.max(0, from - y(base) - 2);
                return <rect key={key} x={x} y={y(base)} width={bar} height={Math.max(height, 1.5)} rx={3} className={`obs-fill obs-fill-${(at % 6) + 1}`} />;
              })}
              {(index % 2 === stacks.length % 2 || stacks.length <= 8) && (
                <text x={x + bar / 2} y={HEIGHT - 6} className="obs-tick" textAnchor="middle">
                  {dayAt(stack.day)}
                </text>
              )}
            </g>
          );
        })}
      </svg>
      <div className="obs-legend">
        {keys.map((key, at) => (
          <span key={key} className={`obs-key obs-key-fill-${(at % 6) + 1}`}>
            {said(key)}
          </span>
        ))}
      </div>
      {hovered !== undefined && on !== null && (
        <div className="obs-tip" style={{ left: `${((LEFT + (on + 0.5) * slot) / WIDTH) * 100}%` }}>
          <div className="obs-tip-head">
            {dayAt(hovered.day)} · {total(hovered)}
          </div>
          {keys
            .filter((key) => (hovered.counts[key] ?? 0) > 0)
            .map((key) => (
              <div key={key} className="obs-tip-row">
                {said(key)} · {hovered.counts[key]}
              </div>
            ))}
        </div>
      )}
    </div>
  );
}
