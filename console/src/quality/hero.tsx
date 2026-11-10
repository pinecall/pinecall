/** Quality's headline: the share of judged calls that kept every rule as a ring, against the window before, the counts under it, and a day at a time the share or the calls that held and broke. */

import { useState, type ReactNode } from "react";
import { Link } from "react-router";

import { DayChart, type Point } from "../dashboard/charts";
import { count, dayLabel, percent } from "../lib/format";
import { type Insights, type WindowDays } from "../lib/insights";
import { StackChart } from "../observability/chart";
import "../observability/observability.css";
import { beforeSaid, windowSaid } from "./window";

/** One of the counts under the ring. */
export interface Figure {
  title: string;
  value: string;
  under: string;
  mood?: "good" | "warn" | "bad" | undefined;
  /** Where it leads; a count with nowhere to go is not a link. */
  to?: string | undefined;
}

function ringOf(share: number | null): string {
  if (share === null) return "var(--raised)";
  const held = share * 100;
  return `conic-gradient(var(--good) 0 ${held}%, color-mix(in srgb, var(--bad) 75%, transparent) ${held}% 100%)`;
}

function Count({ figure }: { figure: Figure }): ReactNode {
  const body = (
    <>
      <span className="dash-eyebrow">{figure.title}</span>
      <span className={figure.mood === undefined ? "dash-part-value" : `dash-part-value dash-mood-${figure.mood}`}>{figure.value}</span>
      <span className="dash-quiet dash-clip">{figure.under}</span>
    </>
  );
  return figure.to === undefined ? (
    <div className="dash-part ql-count">{body}</div>
  ) : (
    <Link to={figure.to} className="dash-part ql-count ql-count-link">
      {body}
    </Link>
  );
}

/** How the share moved against the window before, in points; nothing where either window judged nothing. */
function Moved({ share, was, days }: { share: number | null; was: number | null; days: WindowDays }): ReactNode {
  if (share === null || was === null) return null;
  const points = Math.round((share - was) * 100);
  if (points === 0) return <p className="dash-quiet">The same as {beforeSaid(days)}.</p>;
  return (
    <p className="dash-quiet">
      <span className={points < 0 ? "dash-mood-bad" : "dash-mood-good"}>
        {Math.abs(points)} {Math.abs(points) === 1 ? "point" : "points"} {points < 0 ? "lower" : "higher"}
      </span>{" "}
      than {beforeSaid(days)}.
    </p>
  );
}

export function Hero({ counted, before, days, figures }: { counted: Insights; before: Insights | null; days: WindowDays; figures: readonly Figure[] }): ReactNode {
  const share = counted.judged === 0 ? null : counted.passed / counted.judged;
  const was = before === null || before.judged === 0 ? null : before.passed / before.judged;
  const [drawn, setDrawn] = useState<"share" | "calls">("share");
  const points: Point[] = counted.series.map((day) => ({ label: dayLabel(day.day), value: day.judged === 0 ? null : day.passed / day.judged, detail: `${day.passed} of ${day.judged} calls` }));
  return (
    <div className="ql-top">
      <section className="dash-card ql-hero" aria-label="Calls that kept every rule">
        <div className="ql-hero-main">
          <span className="ql-ring" role="img" aria-label={share === null ? "Nothing judged" : `${percent(share)} kept every rule`}>
            <span className="ql-ring-arc" style={{ background: ringOf(share) }} />
            <span className="ql-ring-value">{share === null ? "—" : percent(share)}</span>
          </span>
          <div className="ql-hero-words">
            <span className="dash-eyebrow">Kept every rule</span>
            <p className="ql-figure">
              {count(counted.passed)} of {count(counted.judged)}
            </p>
            <p className="dash-quiet">Judged calls in {windowSaid(days)}.</p>
            <Moved share={share} was={was} days={days} />
          </div>
        </div>
        <div className="ql-counts">
          {figures.map((figure) => (
            <Count key={figure.title} figure={figure} />
          ))}
        </div>
      </section>
      {points.length > 1 && (
        <section className="dash-card ql-days" aria-label="A day at a time">
          <div className="dash-card-top">
            <span className="dash-eyebrow">{drawn === "share" ? "Kept every rule, a day at a time" : "Judged calls, a day at a time"}</span>
            <div className="dash-switch" role="group" aria-label="What is drawn">
              <button type="button" aria-pressed={drawn === "share"} className={drawn === "share" ? "dash-switch-on" : ""} onClick={() => setDrawn("share")}>
                Share
              </button>
              <button type="button" aria-pressed={drawn === "calls"} className={drawn === "calls" ? "dash-switch-on" : ""} onClick={() => setDrawn("calls")}>
                Calls
              </button>
            </div>
          </div>
          {drawn === "share" ? (
            <DayChart kind="area" points={points} tone="good" top={1} said={percent} nothing="Nothing judged in these days." />
          ) : (
            <StackChart
              stacks={counted.series.map((day) => ({ day: day.day, counts: { held: day.passed, broke: day.judged - day.passed } }))}
              keys={[
                { key: "held", name: "Held", tone: "good" },
                { key: "broke", name: "Broke", tone: "warn" },
              ]}
              nothing="Nothing judged in these days."
            />
          )}
        </section>
      )}
    </div>
  );
}
