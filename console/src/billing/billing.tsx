/** Billing, the organization's page: what it spent this month against its budget and where the month is heading, the way to where it pays, the spend by day and by what it went to, and the plan's limits. */

import { useEffect, useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { DayChart, type Point } from "../dashboard/charts";
import { dayLabel, money } from "../lib/format";
import { useInsights } from "../lib/insights";
import { WORLD } from "../lib/world";
import { spendSplit } from "../observability/fold";
import { PageHead } from "../shell/page-head";
import { readLimits, type Limits } from "../usage/door";
import { meterOf, spent } from "../usage/fold";
import { Meters, ShareBar } from "../usage/meters";
import { billingAddress } from "./door";
import "../dashboard/dashboard.css";
import "../configure/configure.css";
import "../test/test.css";
import "./billing.css";

function hostOf(address: string): string {
  try {
    return new URL(address).host;
  } catch {
    return address;
  }
}

const DAYS = 30;

/** Where the UTC month stands: the day it is on, and how many it has. */
function monthNow(): { day: number; days: number; name: string } {
  const now = new Date();
  return { day: now.getUTCDate(), days: new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() + 1, 0)).getUTCDate(), name: now.toLocaleDateString("en-US", { month: "long", timeZone: "UTC" }) };
}

function Figure({ name, value, note }: { name: string; value: string; note: string }): ReactNode {
  return (
    <div className="dash-figure">
      <span className="dash-dotted">{name}</span>
      <span className="dash-figure-value">{value}</span>
      <span className="dash-quiet dash-clip">{note}</span>
    </div>
  );
}

export function BillingPage(): ReactNode {
  const credentials = useCredentials();
  const [params] = useSearchParams();
  const plan = params.get("plan");
  const [limits, setLimits] = useState<Limits | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  const [opening, setOpening] = useState(plan !== null);

  useEffect(() => {
    readLimits(credentials).then(setLimits, (failed: unknown) => (setOpening(false), setRefused(saidBy(failed))));
  }, [credentials]);

  const billingUrl = limits?.billing_url ?? null;

  // Arrived with a plan picked on the billing page: go back there at once, signed in.
  useEffect(() => {
    if (plan === null || limits === null) return;
    if (billingUrl === null) {
      setOpening(false);
      return;
    }
    let gone = false;
    billingAddress(credentials, billingUrl, plan).then(
      (there) => {
        if (!gone) window.location.replace(there);
      },
      (failed: unknown) => {
        if (!gone) (setOpening(false), setRefused(saidBy(failed)));
      },
    );
    return () => {
      gone = true;
    };
  }, [credentials, plan, limits, billingUrl]);

  const manage = (): void => {
    if (billingUrl === null) return;
    setOpening(true);
    setRefused(null);
    billingAddress(credentials, billingUrl, plan).then(
      (there) => window.location.assign(there),
      (failed: unknown) => (setOpening(false), setRefused(saidBy(failed))),
    );
  };

  const budget = limits === null ? null : meterOf("budget_usd", limits);
  const counted = useInsights(DAYS);
  const month = monthNow();
  const used = limits?.budget_usd.used ?? null;
  const limit = limits?.budget_usd.limit ?? null;
  const pace = used === null ? null : (used / month.day) * month.days;
  const points: Point[] = (counted?.series ?? []).map((day) => ({ label: dayLabel(day.day), value: day.spend_usd }));
  const split = spendSplit(counted?.agents ?? []);
  const splitTotal = split.reduce((sum, part) => sum + part.value, 0);
  const dearest = [...(counted?.series ?? [])].sort((one, other) => other.spend_usd - one.spend_usd)[0];

  return (
    <>
      <PageHead />
      <div className="bil-page">
        {refused !== null && (
          <p className="cfg-refused" role="alert">
            {refused}
          </p>
        )}

        <div className="bil-lead">
          <section className="dash-card bil-card" aria-label="Spent this month">
            <div className="bil-spent">
              <span className="dash-eyebrow">Spent in {month.name}</span>
              <span className="bil-line">
                <span className={`bil-big bil-big-${budget?.mood ?? "calm"}`}>{budget?.used ?? "—"}</span>
                {budget !== null && <span className="dash-quiet">{budget.limit === null ? "No budget set" : `of a ${budget.limit} budget`}</span>}
              </span>
              {budget !== null && budget.share !== null && (
                <span className="bil-budget">
                  <ShareBar share={budget.share} mood={budget.mood} />
                </span>
              )}
            </div>
            <div className="bil-figures">
              <Figure name="A day" value={used === null ? "—" : spent(used / month.day)} note={`Average over ${month.day} ${month.day === 1 ? "day" : "days"}`} />
              <Figure name="At this pace" value={pace === null ? "—" : spent(pace)} note={`By the end of ${month.name}`} />
              <Figure name="Left of the budget" value={used === null || limit === null ? "—" : spent(Math.max(0, limit - used))} note={limit === null ? "No budget set" : pace !== null && pace > limit ? "The pace goes over it" : "The pace stays under it"} />
              <Figure name="Days left" value={String(month.days - month.day)} note="The month is counted in UTC" />
            </div>
          </section>

          <section className="dash-card bil-pay" aria-label="Plan and payment">
            <span className="dash-eyebrow">Plan and payment</span>
            {limits !== null && billingUrl === null && <p className="bil-none">This deployment does not bill. The limits below are the operator's.</p>}
            {billingUrl !== null && (
              <>
                <p className="bil-none">The plan, the card and the invoices live on {hostOf(billingUrl)}. The button opens it signed in as you.</p>
                <button type="button" className="cfg-save bil-manage" disabled={opening} onClick={manage}>
                  {opening ? "Opening billing…" : "Manage plan and payment"}
                </button>
              </>
            )}
            <span className="bil-fill" />
            <Link to="/usage" className="tst-link">
              See what was used, call by call
            </Link>
          </section>
        </div>

        <div className="bil-lead">
          <section className="dash-card" aria-label="Spend a day">
            <div className="dash-card-top">
              <span className="dash-eyebrow">
                Spend a day, last {DAYS} days, {WORLD}
              </span>
              {dearest !== undefined && dearest.spend_usd > 0 && (
                <span className="dash-quiet">
                  The most, {money(dearest.spend_usd)} on {dayLabel(dearest.day)}
                </span>
              )}
            </div>
            <DayChart kind="bars" points={points} tone="blue" said={spent} nothing={counted === null ? "Reading…" : "No spend in these days."} />
          </section>

          <section className="dash-card" aria-label="Where it went">
            <div className="dash-card-top">
              <span className="dash-eyebrow">Where it went</span>
              <span className="dash-quiet">{counted === null ? "" : money(splitTotal)}</span>
            </div>
            {splitTotal === 0 ? (
              <p className="dash-empty">{counted === null ? "Reading…" : "No spend in these days."}</p>
            ) : (
              <>
                <div className="dash-split-bar" aria-hidden="true">
                  {split.filter((part) => part.value > 0).map((part) => (
                    <span key={part.name} className={`dash-tone-${part.tone}`} style={{ flexGrow: part.value }} />
                  ))}
                </div>
                <ul className="dash-legend">
                  {split.map((part) => (
                    <li key={part.name} className="dash-legend-row">
                      <span className={`dash-legend-dot dash-tone-${part.tone}`} aria-hidden="true" />
                      <span className="dash-legend-name">{part.name}</span>
                      <span className="dash-quiet">{Math.round((part.value / splitTotal) * 100)}%</span>
                      <span className="dash-legend-count bil-part">{spent(part.value)}</span>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </section>
        </div>

        <Meters limits={limits} />
      </div>
    </>
  );
}
