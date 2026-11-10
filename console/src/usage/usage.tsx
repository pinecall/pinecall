/** Usage, the organization's page: its quotas this month, and what was used by day, by agent and by call. */

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { AvatarOf } from "../apps/avatar";
import { DayChart, type Point } from "../dashboard/charts";
import { ago, count, dayLabel, percent, utcDay } from "../lib/format";
import { Icon, type IconName } from "../shell/icons";
import { PageHead } from "../shell/page-head";
import { readLimits, readUsage, type Limits, type UsageRow } from "./door";
import { byAgent, byCall, costliest, lastDays, measured, saidOf, spent, total, type Measure } from "./fold";
import { Meters, ShareBar } from "./meters";
import "../dashboard/dashboard.css";
import "../configure/configure.css";
import "../apps/apps.css";
import "../test/test.css";
import "./usage.css";

const MEASURES: readonly { value: Measure; name: string }[] = [
  { value: "cost", name: "Cost" },
  { value: "minutes", name: "Minutes" },
  { value: "calls", name: "Calls" },
];

const DAYS_DRAWN = 30;
const CALLS_LISTED = 10;
// The feed runs oldest first, 500 rows a page: it is followed to its end, this many pages before asking.
const PAGES_AT_ONCE = 40;

function Head({ icon, title, about, children }: { icon: IconName; title: string; about: string; children?: ReactNode }): ReactNode {
  return (
    <header className="tst-head">
      <span className="tst-head-mark" aria-hidden="true">
        <Icon name={icon} size={16} />
      </span>
      <span className="tst-head-words">
        <span className="tst-head-title">{title}</span>
        <span className="tst-head-about">{about}</span>
      </span>
      {children}
    </header>
  );
}

function Total({ label, value, under }: { label: string; value: string; under: string }): ReactNode {
  return (
    <div className="usg-total">
      <span className="dash-eyebrow">{label}</span>
      <span className="dash-big">{value}</span>
      <span className="dash-quiet dash-clip">{under}</span>
    </div>
  );
}

export function UsagePage(): ReactNode {
  const credentials = useCredentials();
  const [limits, setLimits] = useState<Limits | null>(null);
  const [rows, setRows] = useState<UsageRow[] | null>(null);
  const [next, setNext] = useState<number | null>(null);
  const [from, setFrom] = useState(0);
  const [reading, setReading] = useState(true);
  const [refused, setRefused] = useState<string | null>(null);
  const [measure, setMeasure] = useState<Measure>("cost");

  useEffect(() => {
    readLimits(credentials).then(setLimits, (failed: unknown) => setRefused(saidBy(failed)));
  }, [credentials]);

  useEffect(() => {
    let gone = false;
    setReading(true);
    if (from === 0) setRows(null);
    void (async () => {
      try {
        let after = from;
        for (let page = 0; page < PAGES_AT_ONCE; page += 1) {
          const answer = await readUsage(credentials, after);
          if (gone) return;
          setRows((was) => [...(was ?? []), ...answer.rows]);
          setNext(answer.next);
          if (answer.next === null) break;
          after = answer.next;
        }
      } catch (failed) {
        if (gone) return;
        setRefused(saidBy(failed));
        setRows((was) => was ?? []);
      }
      if (!gone) setReading(false);
    })();
    return () => {
      gone = true;
    };
  }, [credentials, from]);

  const bills = useMemo(() => byCall(rows ?? []), [rows]);
  const all = useMemo(() => total(bills), [bills]);
  const agents = useMemo(() => byAgent(bills, measure), [bills, measure]);
  const dear = useMemo(() => costliest(bills, CALLS_LISTED), [bills]);
  const days = useMemo(() => lastDays(bills, DAYS_DRAWN, Date.now() / 1000), [bills]);
  const points: Point[] = days.map((day) => ({ label: dayLabel(day.name), value: measured(day, measure), detail: measure === "calls" ? spent(day.cost_usd) : `${count(day.calls)} ${day.calls === 1 ? "call" : "calls"}` }));
  const whole = measured(all, measure);
  const first = bills.reduce<number | null>((least, bill) => (least === null || bill.at < least ? bill.at : least), null);
  const blank = rows === null ? "—" : null;
  const through = !reading && next === null;

  return (
    <>
      <PageHead />
      <div className="usg-page">
        {refused !== null && (
          <p className="cfg-refused" role="alert">
            {refused}
          </p>
        )}

        <section className="dash-card usg-totals" aria-label="Totals">
          <Total label="Cost" value={blank ?? spent(all.cost_usd)} under={all.caller_cost_usd > 0 ? `+ ${spent(all.caller_cost_usd)} simulated callers` : first === null ? "Nothing metered yet" : `Since ${dayLabel(utcDay(first))}`} />
          <Total label="Calls" value={blank ?? count(all.calls)} under={all.simulations > 0 ? `${count(all.simulations)} simulated` : "None simulated"} />
          <Total label="Minutes" value={blank ?? all.minutes.toFixed(1)} under={all.lent_minutes > 0 ? `${all.lent_minutes.toFixed(1)} on the platform's keys` : "All on your keys"} />
          <Total label="Per call" value={blank ?? (all.calls === 0 ? "—" : spent(all.cost_usd / all.calls))} under={all.minutes === 0 ? "No minutes yet" : `${spent(all.cost_usd / all.minutes)} a minute`} />
          <Total label="LLM tokens" value={blank ?? count(all.tokens)} under={`${count(all.messages)} messages`} />
        </section>

        <Meters limits={limits} />

        <section className="dash-card usg-chart" aria-label="A day at a time">
          <div className="dash-card-top">
            <span className="dash-eyebrow">A day at a time, last {DAYS_DRAWN} days</span>
            <div className="dash-switch" role="group" aria-label="What is measured">
              {MEASURES.map((one) => (
                <button key={one.value} type="button" aria-pressed={one.value === measure} className={one.value === measure ? "dash-switch-on" : ""} onClick={() => setMeasure(one.value)}>
                  {one.name}
                </button>
              ))}
            </div>
          </div>
          <DayChart kind="bars" points={points} tone={measure === "cost" ? "blue" : measure === "minutes" ? "good" : "accent"} said={(value) => (measure === "minutes" ? value.toFixed(value < 10 ? 1 : 0) : saidOf(measure, value))} nothing={rows === null ? "Reading…" : "Nothing metered in these days."} />
        </section>

        <div className="usg-pair">
          <section className="tst-list usg-tone-accent" aria-label="By agent">
            <Head icon="agents" title="By agent" about={`Each agent's share of the ${measure === "cost" ? "cost" : measure}.`}>
              {agents.length > 0 && <span className="tst-head-stands">{agents.length}</span>}
            </Head>
            {rows === null && <p className="dash-quiet tst-none">Reading…</p>}
            {rows !== null && agents.length === 0 && <p className="dash-quiet tst-none">Nothing metered yet.</p>}
            {agents.map((agent) => {
              const share = whole === 0 ? 0 : measured(agent, measure) / whole;
              return (
                <div key={agent.name} className="tst-row">
                  <div className="tst-row-main usg-still">
                    <AvatarOf name={agent.name} size={32} />
                    <span className="tst-row-words">
                      <span className="tst-row-name">
                        <span className="dash-clip">{agent.name}</span>
                      </span>
                      <span className="tst-row-under dash-clip">
                        {count(agent.calls)} {agent.calls === 1 ? "call" : "calls"}, {agent.minutes.toFixed(1)} min, {spent(agent.cost_usd)}
                      </span>
                    </span>
                    <span className="usg-side">
                      <span className="usg-value">
                        {saidOf(measure, measured(agent, measure))}
                        <span className="usg-of">{percent(share)}</span>
                      </span>
                      <ShareBar share={share} />
                    </span>
                  </div>
                </div>
              );
            })}
          </section>

          <section className="tst-list tst-tone-gold" aria-label="Most expensive calls">
            <Head icon="coins" title="Most expensive calls" about="The calls that cost the most." />
            {rows === null && <p className="dash-quiet tst-none">Reading…</p>}
            {rows !== null && dear.length === 0 && <p className="dash-quiet tst-none">No call has cost anything yet.</p>}
            {dear.map((bill) => (
              <div key={bill.call} className="tst-row">
                <Link to={`/calls/${encodeURIComponent(bill.call)}`} className="tst-row-main">
                  <AvatarOf name={bill.agent} size={32} />
                  <span className="tst-row-words">
                    <span className="tst-row-name">
                      <span className="dash-clip">{bill.agent}</span>
                      {bill.simulations > 0 && <span className="tst-tag">simulated</span>}
                    </span>
                    <span className="tst-row-under dash-clip">
                      <span className="usg-id">{bill.call}</span>, {bill.minutes.toFixed(1)} min
                    </span>
                  </span>
                  <span className="tst-row-when">{ago(bill.at)}</span>
                  <span className="usg-value">{spent(bill.cost_usd)}</span>
                </Link>
              </div>
            ))}
          </section>
        </div>

        {rows !== null && !through && (
          <button type="button" className="app-button usg-more" disabled={reading || next === null} onClick={() => next !== null && setFrom(next)}>
            {reading ? `Reading… ${count(rows.length)} rows` : `Load more, ${count(rows.length)} rows read`}
          </button>
        )}
      </div>
    </>
  );
}
