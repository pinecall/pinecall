/** Quality's numbers across: the share of calls that kept every rule as a ring, a bar a day under it, and three cards — what broke, the fixes ready, the goldens. */

import type { ReactNode } from "react";
import { Link } from "react-router";

import { dayOf } from "../../lib/format";
import { type Insights, type WindowDays } from "../../lib/insights";

// The window before, as the sentence says it.
const BEFORE: Record<WindowDays, string> = { 1: "the day before", 7: "the week before", 30: "the 30 days before" };

/** The ring and its sentence: how many of the judged calls held, against the window before. */
export function Kept({ counted, before, days }: { counted: Insights | null; before: Insights | null; days: WindowDays }): ReactNode {
  const judged = counted?.judged ?? 0;
  const share = counted === null || judged === 0 ? null : counted.passed / judged;
  const was = before === null || before.judged === 0 ? null : before.passed / before.judged;
  const points = share === null || was === null ? null : Math.round((share - was) * 100);
  return (
    <div className="qly-kept">
      <Ring share={share} />
      <div className="qly-kept-words">
        <span className="qly-kept-title">of calls kept every rule</span>
        <span className="qly-kept-sub">
          {counted === null ? "Counting the verdicts…" : judged === 0 ? "No call was judged in this window." : `${counted.passed} of ${judged} judged calls`}
          {points !== null && points !== 0 && (
            <>
              {" · "}
              <span className={points < 0 ? "qly-down" : "qly-up"}>
                {Math.abs(points)} pts {points < 0 ? "lower" : "higher"}
              </span>{" "}
              than {BEFORE[days]}
            </>
          )}
          {points === 0 && ` · the same as ${BEFORE[days]}`}
        </span>
        {counted !== null && counted.series.length > 1 && <DayBars series={counted.series} />}
      </div>
    </div>
  );
}

/** The share as a ring, drawn on a hundred units of circumference so the dash is the percentage. */
function Ring({ share }: { share: number | null }): ReactNode {
  return (
    <span className="qly-ring" role="img" aria-label={share === null ? "nothing judged" : `${Math.round(share * 100)}% kept every rule`}>
      <svg viewBox="0 0 36 36">
        <circle cx="18" cy="18" r="15.5" className="qly-ring-track" />
        {share !== null && share > 0 && <circle cx="18" cy="18" r="15.5" className="qly-ring-fill" pathLength={100} strokeDasharray={`${share * 100} 100`} />}
      </svg>
      <span className="qly-ring-value">{share === null ? "—" : `${Math.round(share * 100)}%`}</span>
    </span>
  );
}

/** A bar a day, as tall as the share that held that day; the newest day solid. A day nobody judged is a stub. */
function DayBars({ series }: { series: Insights["series"] }): ReactNode {
  return (
    <span className="qly-days" aria-hidden>
      {series.map((day, index) => {
        const share = day.judged === 0 ? null : day.passed / day.judged;
        const at = dayOf(Date.parse(`${day.day}T12:00:00Z`) / 1000);
        return (
          <span
            key={day.day}
            className={share === null ? "qly-day qly-day-none" : index === series.length - 1 ? "qly-day qly-day-now" : "qly-day"}
            style={{ height: `${share === null ? 12 : Math.max(20, share * 100)}%` }}
            title={share === null ? `${at} · nothing judged` : `${at} · ${day.passed} of ${day.judged} held`}
          />
        );
      })}
    </span>
  );
}

/** One of the three cards beside the ring: a label, a number in its tone, a line under it; a link when it leads somewhere. */
export function Count({ label, value, tone, sub, to }: { label: string; value: string; tone?: "red" | "amber" | "green" | undefined; sub: string; to?: string | undefined }): ReactNode {
  const body = (
    <>
      <span className="qly-count-label">{label}</span>
      <span className={tone === undefined ? "qly-count-value" : `qly-count-value qly-count-${tone}`}>{value}</span>
      <span className="qly-count-sub">{sub}</span>
    </>
  );
  return to === undefined ? (
    <div className="qly-count">{body}</div>
  ) : (
    <Link to={to} className="qly-count qly-count-link">
      {body}
    </Link>
  );
}
