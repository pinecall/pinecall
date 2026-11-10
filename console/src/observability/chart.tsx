/** Observability's graphs over the window's days, on the dashboard's plot: several lines with a reading under the pointer, and bars stacked by key. */

import { useState, type ReactNode } from "react";

import { curveThrough, roomFor, runsOf, type At, type Tone } from "../dashboard/charts";
import { dayLabel } from "../lib/format";

export interface Line {
  name: string;
  tone: Tone;
  /** One value a day, null where the day has nothing to say. */
  values: readonly (number | null)[];
}

/** A level drawn across the plot: the line a monitor watches. */
export interface Mark {
  at: number;
  name: string;
}

// A label on every day of a short window, on a regular few of a long one.
const labelEvery = (days: number): number => (days > 14 ? 5 : 1);

function Frame({ days, room, said, read, onRead, reading, legend, children }: { days: readonly string[]; room: number; said: (value: number) => string; read: number | null; onRead: (at: number | null) => void; reading: ReactNode; legend: readonly { name: string; tone: Tone }[]; children: ReactNode }): ReactNode {
  const readAt = read === null ? 0 : ((read + 0.5) / days.length) * 100;
  const step = labelEvery(days.length);
  return (
    <div className="ob-chart">
      <div className="dash-plot" onMouseLeave={() => onRead(null)}>
        {[1, 0.5, 0].map((share) => (
          <div key={share} className="dash-grid" style={{ bottom: `${share * 100}%` }}>
            <span className="dash-grid-label">{said(room * share)}</span>
          </div>
        ))}
        <div className="dash-draw">
          {children}
          {read !== null && (
            <div className="dash-reading ob-reading" style={{ left: `${readAt}%`, transform: `translateX(${readAt > 60 ? "-100%" : readAt < 40 ? "0" : "-50%"})` }}>
              <span className="dash-reading-day">{dayLabel(days[read] ?? "")}</span>
              {reading}
            </div>
          )}
        </div>
      </div>
      <div className="dash-days" aria-hidden="true">
        {days.map((day, at) => (
          <span key={day} className="dash-day">
            {at % step === 0 ? dayLabel(day) : ""}
          </span>
        ))}
      </div>
      {legend.length > 1 && (
        <div className="dash-keys ob-keys">
          {legend.map((one) => (
            <span key={one.name} className="dash-key">
              <span className={`dash-key-dot dash-tone-${one.tone}`} aria-hidden="true" />
              <span className="dash-first">{one.name}</span>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function ReadingRow({ name, tone, value }: { name: string; tone: Tone; value: string }): ReactNode {
  return (
    <span className="ob-reading-row">
      <span className={`dash-key-dot dash-tone-${tone}`} aria-hidden="true" />
      <span className="dash-first">{name}</span>
      <b>{value}</b>
    </span>
  );
}

/** Solid between days that follow each other, dashed across the days with nothing; `top` fixes the scale, as a share's 100% does. */
export function LinesChart({ days, lines, said, top, mark, nothing }: { days: readonly string[]; lines: readonly Line[]; said: (value: number) => string; top?: number; mark?: Mark | undefined; nothing: string }): ReactNode {
  const [read, setRead] = useState<number | null>(null);
  const known = lines.flatMap((line) => line.values.filter((value): value is number => value !== null));
  if (known.length === 0) return <p className="dash-empty">{nothing}</p>;
  const room = top ?? roomFor(Math.max(...known, mark?.at ?? 0));
  const place = (value: number | null | undefined, at: number): At | null => (value == null ? null : { x: ((at + 0.5) / days.length) * 100, y: 100 - (value / room) * 100 });
  const drawn = lines.map((line) => {
    const placed = days.map((_, at) => place(line.values[at], at));
    const runs = runsOf(placed);
    const bridges = runs.slice(1).flatMap((run, at) => {
      const from = runs[at]?.at(-1);
      const to = run[0];
      return from === undefined || to === undefined ? [] : [`M${from.x} ${from.y}L${to.x} ${to.y}`];
    });
    return { line, placed, runs, bridges };
  });
  const reading = read === null ? null : lines.map((line) => <ReadingRow key={line.name} name={line.name} tone={line.tone} value={line.values[read] == null ? "—" : said(line.values[read] ?? 0)} />);

  return (
    <Frame days={days} room={room} said={said} read={read} onRead={setRead} reading={reading} legend={lines}>
      <svg className="dash-svg" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
        {drawn.map(({ line, runs, bridges }) => (
          <g key={line.name} fill="none" stroke={`var(--${line.tone})`} vectorEffect="non-scaling-stroke">
            {bridges.map((path) => (
              <path key={path} d={path} strokeWidth="1.5" strokeDasharray="3 4" opacity="0.6" vectorEffect="non-scaling-stroke" />
            ))}
            {runs.map((run) => (run.length < 2 ? null : <path key={run[0]?.x} d={curveThrough(run)} strokeWidth="2" strokeLinecap="round" vectorEffect="non-scaling-stroke" />))}
          </g>
        ))}
      </svg>
      {mark !== undefined && (
        <div className={mark.at / room > 0.8 ? "ob-mark ob-mark-under" : "ob-mark"} style={{ bottom: `${Math.min(100, (mark.at / room) * 100)}%` }}>
          <span>
            {mark.name} {said(mark.at)}
          </span>
        </div>
      )}
      <div className="dash-columns">
        {days.map((day, at) => (
          <div key={day} className="dash-column" onMouseEnter={() => setRead(at)} />
        ))}
      </div>
      {read !== null && <span className="dash-rule" style={{ left: `${((read + 0.5) / days.length) * 100}%` }} />}
      {drawn.map(({ line, placed }) =>
        placed.map((one, at) => {
          // A day alone between two empty ones has no line through it: its point is always drawn.
          const alone = one !== null && placed[at - 1] == null && placed[at + 1] == null;
          if (one === null || (read !== at && !alone)) return null;
          return <span key={`${line.name}-${at}`} className={read === at ? "dash-point dash-point-read" : "dash-point"} style={{ left: `${one.x}%`, top: `${one.y}%`, borderColor: `var(--${line.tone})` }} />;
        }),
      )}
    </Frame>
  );
}

export interface StackKey {
  key: string;
  name: string;
  tone: Tone;
}

/** One day's bar: a count per key. */
export interface Stack {
  day: string;
  counts: Readonly<Record<string, number>>;
}

const sumOf = (stack: Stack): number => Object.values(stack.counts).reduce((sum, count) => sum + count, 0);

/** One bar a day, its keys stacked from the first up. */
export function StackChart({ stacks, keys, nothing }: { stacks: readonly Stack[]; keys: readonly StackKey[]; nothing: string }): ReactNode {
  const [read, setRead] = useState<number | null>(null);
  const totals = stacks.map(sumOf);
  if (totals.every((total) => total === 0)) return <p className="dash-empty">{nothing}</p>;
  const room = Math.max(2, roomFor(Math.max(...totals)));
  const hovered = read === null ? undefined : stacks[read];
  const reading =
    hovered === undefined ? null : (
      <>
        <span className="dash-reading-value">{sumOf(hovered)}</span>
        {keys
          .filter((one) => (hovered.counts[one.key] ?? 0) > 0)
          .map((one) => (
            <ReadingRow key={one.key} name={one.name} tone={one.tone} value={String(hovered.counts[one.key] ?? 0)} />
          ))}
      </>
    );
  return (
    <Frame days={stacks.map((stack) => stack.day)} room={room} said={(value) => String(Math.round(value))} read={read} onRead={setRead} reading={reading} legend={keys}>
      <div className="dash-columns">
        {stacks.map((stack, at) => (
          <div key={stack.day} className="dash-column" onMouseEnter={() => setRead(at)}>
            <span className={read === at ? "ob-stack ob-stack-read" : "ob-stack"} style={{ height: `${((totals[at] ?? 0) / room) * 100}%` }}>
              {keys.map((one) => {
                const count = stack.counts[one.key] ?? 0;
                return count === 0 ? null : <span key={one.key} className={`dash-tone-${one.tone}`} style={{ flexGrow: count }} />;
              })}
            </span>
          </div>
        ))}
      </div>
    </Frame>
  );
}
