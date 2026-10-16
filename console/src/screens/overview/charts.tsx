/** The Overview's charts, drawn in SVG with the console's own tokens: calls a day by channel, and a bar per share. */

import { useState, type ReactNode } from "react";

import { dayOf } from "../../lib/format";
import { callsOn, CHANNELS, type Channel, type Day } from "./counted";

const WIDTH = 640;
const HEIGHT = 180;
const LEFT = 30;
const BOTTOM = 22;
const TOP = 8;
const PLOT = HEIGHT - BOTTOM - TOP;

/** The channel's name as a legend and a tooltip say it. */
export const CHANNEL_NAME: Record<Channel, string> = { phone: "Phone", web: "Web", whatsapp: "WhatsApp" };

/** Three ticks from zero to a round top: what the y axis is labelled with. */
function ticksFor(most: number): number[] {
  const step = Math.max(1, Math.ceil(most / 3));
  return [0, step, step * 2, step * 3];
}

function dayAt(day: string): string {
  return dayOf(Date.parse(`${day}T12:00:00Z`) / 1000);
}

/** Calls a day, each bar its channels stacked with a 2px gap between them; a hover says the day's numbers. */
export function CallsByDay({ days }: { days: Day[] }): ReactNode {
  const [on, setOn] = useState<number | null>(null);
  const ticks = ticksFor(Math.max(1, ...days.map(callsOn)));
  const top = ticks[ticks.length - 1] ?? 1;
  const slot = (WIDTH - LEFT) / days.length;
  const bar = Math.min(26, slot * 0.62);
  const y = (value: number): number => TOP + PLOT - (value / top) * PLOT;
  const hovered = on === null ? undefined : days[on];

  return (
    <div className="ovw-chart">
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label="Calls a day, by channel" onMouseLeave={() => setOn(null)}>
        {ticks.map((tick) => (
          <g key={tick}>
            <line x1={LEFT} x2={WIDTH} y1={y(tick)} y2={y(tick)} className="ovw-grid" />
            <text x={LEFT - 8} y={y(tick) + 3.5} className="ovw-tick" textAnchor="end">
              {tick}
            </text>
          </g>
        ))}
        {days.map((day, index) => {
          const x = LEFT + index * slot + (slot - bar) / 2;
          let base = 0;
          return (
            <g key={day.day} onMouseEnter={() => setOn(index)} className={on === index ? "ovw-bar ovw-bar-on" : "ovw-bar"}>
              {/* The hit target is the whole slot, taller than any bar. */}
              <rect x={LEFT + index * slot} y={TOP} width={slot} height={PLOT} className="ovw-hit" />
              {CHANNELS.map((channel) => {
                const value = day.calls[channel];
                if (value === 0) return null;
                const from = y(base);
                base += value;
                const height = Math.max(0, from - y(base) - 2);
                return <rect key={channel} x={x} y={y(base)} width={bar} height={Math.max(height, 1.5)} rx={3} className={`ovw-fill ovw-fill-${channel}`} />;
              })}
              {(index % 2 === days.length % 2 || days.length <= 8) && (
                <text x={x + bar / 2} y={HEIGHT - 6} className="ovw-tick" textAnchor="middle">
                  {dayAt(day.day)}
                </text>
              )}
            </g>
          );
        })}
      </svg>
      {hovered !== undefined && on !== null && (
        <div className="ovw-tip" style={{ left: `${((LEFT + (on + 0.5) * slot) / WIDTH) * 100}%` }}>
          <div className="ovw-tip-head">
            {dayAt(hovered.day)} · {callsOn(hovered)} calls
          </div>
          {CHANNELS.filter((channel) => hovered.calls[channel] > 0).map((channel) => (
            <div key={channel} className="ovw-tip-row">
              <span className={`ovw-key ovw-key-${channel}`} />
              {CHANNEL_NAME[channel]}
              <span className="ovw-tip-value">{hovered.calls[channel]}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/** A labelled bar per row, its share of the largest: how calls ended, which door they came in by. */
export function Shares({ rows, tone }: { rows: { name: string; count: number; key?: string | undefined }[]; tone?: "accent" | "channel" | undefined }): ReactNode {
  const most = Math.max(1, ...rows.map((row) => row.count));
  const total = rows.reduce((all, row) => all + row.count, 0);
  return (
    <div className="ovw-shares">
      {rows.map((row) => (
        <div key={row.name} className="ovw-share">
          <span className="ovw-share-name">{row.name}</span>
          <span className="ovw-share-track">
            <span
              className={tone === "channel" && row.key !== undefined ? `ovw-share-fill ovw-fill-${row.key}` : "ovw-share-fill"}
              style={{ width: `${Math.max(2, (row.count / most) * 100)}%` }}
            />
          </span>
          <span className="ovw-share-count">
            {row.count}
            <span className="ovw-share-pct">{total === 0 ? "" : ` · ${Math.round((row.count / total) * 100)}%`}</span>
          </span>
        </div>
      ))}
    </div>
  );
}

/** The channels as a legend: a swatch and a name each, so no series is told by colour alone. */
export function Legend(): ReactNode {
  return (
    <span className="ovw-legend">
      {CHANNELS.map((channel) => (
        <span key={channel} className="ovw-legend-item">
          <span className={`ovw-key ovw-key-${channel}`} />
          {CHANNEL_NAME[channel]}
        </span>
      ))}
    </span>
  );
}
