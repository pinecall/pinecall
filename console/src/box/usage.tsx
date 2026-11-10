/** Box usage, the operator's page: what the whole deployment used, who used the most of it, and a day at a time. */

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { DayChart, type Point } from "../dashboard/charts";
import { ago, count, dayLabel, percent, utcDay } from "../lib/format";
import { useOrg } from "../lib/org";
import { Icon } from "../shell/icons";
import { PageHead } from "../shell/page-head";
import { measured, saidOf, spent, type Measure } from "../usage/fold";
import { ShareBar } from "../usage/meters";
import { readOrgs, type Org } from "./door";
import { readBoxUsage, type BoxUsageRow } from "./usage-door";
import { DAYS, daysOf, fold, within, type OrgUse, type Window } from "./usage-fold";
import "../dashboard/dashboard.css";
import "../configure/configure.css";
import "../apps/apps.css";
import "../test/test.css";
import "../usage/usage.css";
import "./usage.css";

const MEASURES: readonly { value: Measure; name: string; word: string }[] = [
  { value: "cost", name: "Cost", word: "cost" },
  { value: "minutes", name: "Minutes", word: "minutes" },
  { value: "calls", name: "Calls", word: "calls" },
];

const WINDOWS: readonly { value: Window; name: string; said: string }[] = [
  { value: "week", name: "7 days", said: "in the last 7 days" },
  { value: "month", name: "30 days", said: "in the last 30 days" },
  { value: "all", name: "All time", said: "since the first call metered" },
];

// The feed runs oldest first, 500 rows a page: it is followed to its end, this many pages before asking.
const PAGES_AT_ONCE = 40;

const plural = (many: number, one: string, more: string): string => `${count(many)} ${many === 1 ? one : more}`;

function Total({ label, value, under }: { label: string; value: string; under: string }): ReactNode {
  return (
    <div className="bxu-total">
      <span className="dash-eyebrow">{label}</span>
      <span className="dash-big">{value}</span>
      <span className="dash-quiet dash-clip">{under}</span>
    </div>
  );
}

function Mark({ name }: { name: string }): ReactNode {
  return (
    <span className="tst-mark" aria-hidden="true">
      {name.trim().charAt(0).toUpperCase()}
    </span>
  );
}

function OrgRow({ use, org, share, measure }: { use: OrgUse; org: Org | undefined; share: number; measure: Measure }): ReactNode {
  const inside = (
    <>
      <Mark name={org?.name ?? use.org} />
      <span className="tst-row-words">
        <span className="tst-row-name">
          <span className="dash-clip">{org?.name ?? use.org}</span>
          <span className="tst-tag">{org === undefined ? "no longer an organization" : org.slug}</span>
        </span>
        <span className="tst-row-under dash-clip">
          {plural(use.calls, "call", "calls")}, {use.minutes.toFixed(1)} min, {spent(use.cost_usd)}, {plural(use.agents, "agent", "agents")}
        </span>
      </span>
      <span className="tst-row-when">Last used {ago(use.last)}</span>
      <span className="usg-side">
        <span className="usg-value">
          {saidOf(measure, measured(use, measure))}
          <span className="usg-of">{percent(share)}</span>
        </span>
        <ShareBar share={share} />
      </span>
    </>
  );
  return (
    <div className="tst-row">
      {org === undefined ? (
        <div className="tst-row-main bxu-still">{inside}</div>
      ) : (
        <Link to={`/box/orgs/${encodeURIComponent(org.slug)}`} className="tst-row-main bxu-row">
          {inside}
        </Link>
      )}
    </div>
  );
}

function BoxUsage(): ReactNode {
  const credentials = useCredentials();
  const [orgs, setOrgs] = useState<Org[] | null>(null);
  const [rows, setRows] = useState<BoxUsageRow[] | null>(null);
  const [next, setNext] = useState<number | null>(null);
  const [from, setFrom] = useState(0);
  const [reading, setReading] = useState(true);
  const [refused, setRefused] = useState<string | null>(null);
  const [measure, setMeasure] = useState<Measure>("cost");
  const [span, setSpan] = useState<Window>("month");
  const [idleShown, setIdleShown] = useState(false);

  useEffect(() => {
    // The feed names an organization by its id: without the list a row still reads, under the id.
    readOrgs(credentials).then(setOrgs, (failed: unknown) => (setOrgs([]), setRefused(saidBy(failed))));
  }, [credentials]);

  useEffect(() => {
    let gone = false;
    setReading(true);
    if (from === 0) setRows(null);
    void (async () => {
      try {
        let after = from;
        for (let page = 0; page < PAGES_AT_ONCE; page += 1) {
          const answer = await readBoxUsage(credentials, after);
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

  const inWindow = useMemo(() => within(rows ?? [], span, Date.now() / 1000), [rows, span]);
  const { orgs: used, all, bills } = useMemo(() => fold(inWindow, measure), [inWindow, measure]);
  const days = useMemo(() => daysOf(bills, span, Date.now() / 1000), [bills, span]);
  const byId = useMemo(() => new Map((orgs ?? []).map((one) => [one.id, one])), [orgs]);
  const idle = useMemo(() => (orgs ?? []).filter((one) => !used.some((use) => use.org === one.id)), [orgs, used]);

  const said = WINDOWS.find((one) => one.value === span)?.said ?? "";
  const word = MEASURES.find((one) => one.value === measure)?.word ?? measure;
  const whole = measured(all, measure);
  const points: Point[] = days.map((day) => ({ label: dayLabel(day.name), value: measured(day, measure), detail: measure === "calls" ? spent(day.cost_usd) : plural(day.calls, "call", "calls") }));
  const first = (rows ?? []).reduce<number | null>((least, row) => (least === null || row.at < least ? row.at : least), null);
  const blank = rows === null ? "—" : null;
  const through = !reading && next === null;
  const top = used[0];
  const topShare = top === undefined || whole === 0 ? 0 : measured(top, measure) / whole;
  const topName = top === undefined ? "" : (byId.get(top.org)?.name ?? top.org);

  return (
    <div className="tst bxu">
      {refused !== null && (
        <p className="cfg-refused" role="alert">
          {refused}
        </p>
      )}

      <div className="bxu-tools">
        <div className="dash-switch" role="group" aria-label="How far back">
          {WINDOWS.map((one) => (
            <button key={one.value} type="button" aria-pressed={one.value === span} className={one.value === span ? "dash-switch-on" : ""} onClick={() => setSpan(one.value)}>
              {one.name}
            </button>
          ))}
        </div>
        <div className="dash-switch" role="group" aria-label="What is measured">
          {MEASURES.map((one) => (
            <button key={one.value} type="button" aria-pressed={one.value === measure} className={one.value === measure ? "dash-switch-on" : ""} onClick={() => setMeasure(one.value)}>
              {one.name}
            </button>
          ))}
        </div>
      </div>

      <section className="dash-card bxu-lead" aria-label="Totals">
        <div className="bxu-says">
          <span className="bxu-says-title">{rows === null ? "Reading what was used…" : top === undefined ? `Nothing was used ${said}` : used.length === 1 ? `${topName} is the only organization that used the deployment` : `${topName} used the most: ${percent(topShare)} of the ${word}`}</span>
          <span className="dash-quiet">
            {rows !== null && orgs !== null && `${count(used.length)} of ${plural(Math.max(orgs.length, used.length), "organization", "organizations")} used it ${said}. `}
            Both environments together. Cost is what the vendors charged, not what you bill.
          </span>
        </div>
        <div className="bxu-totals">
          <Total label="Cost" value={blank ?? spent(all.cost_usd)} under={all.caller_cost_usd > 0 ? `+ ${spent(all.caller_cost_usd)} simulated callers` : span === "all" && first !== null ? `Since ${dayLabel(utcDay(first))}` : "Paid to the vendors"} />
          <Total label="Calls" value={blank ?? count(all.calls)} under={all.simulations > 0 ? `${count(all.simulations)} simulated` : "None simulated"} />
          <Total label="Minutes" value={blank ?? all.minutes.toFixed(1)} under={all.lent_minutes > 0 ? `${all.lent_minutes.toFixed(1)} on the platform's keys` : "None on the platform's keys"} />
          <Total label="Per call" value={blank ?? (all.calls === 0 ? "—" : spent(all.cost_usd / all.calls))} under={all.minutes === 0 ? "No minutes yet" : `${spent(all.cost_usd / all.minutes)} a minute`} />
          <Total label="LLM tokens" value={blank ?? count(all.tokens)} under={plural(all.messages, "message", "messages")} />
        </div>
      </section>

      <section className="dash-card bxu-chart" aria-label="A day at a time">
        <div className="dash-card-top">
          <span className="dash-eyebrow">
            {word} a day, last {DAYS[span] ?? 30} days
          </span>
          <span className="dash-quiet">Days are UTC</span>
        </div>
        <DayChart kind="bars" points={points} tone={measure === "cost" ? "blue" : measure === "minutes" ? "good" : "accent"} said={(value) => (measure === "minutes" ? value.toFixed(value < 10 ? 1 : 0) : saidOf(measure, value))} nothing={rows === null ? "Reading…" : "Nothing metered in these days."} />
      </section>

      <section className="tst-list bxu-orgs" aria-label="By organization">
        <header className="tst-head">
          <span className="tst-head-mark" aria-hidden="true">
            <Icon name="building" size={16} />
          </span>
          <span className="tst-head-words">
            <span className="tst-head-title">By organization</span>
            <span className="tst-head-about">
              Who used the most {word} {said}, and each one's share of the whole. Open one for its limits.
            </span>
          </span>
          {used.length > 0 && <span className="tst-head-stands">{plural(used.length, "organization", "organizations")}</span>}
        </header>
        {rows === null && <p className="dash-quiet tst-none">Reading…</p>}
        {rows !== null && used.length === 0 && <p className="dash-quiet tst-none">No organization used anything {said}.</p>}
        {used.map((use) => (
          <OrgRow key={use.org} use={use} org={byId.get(use.org)} share={whole === 0 ? 0 : measured(use, measure) / whole} measure={measure} />
        ))}
        {rows !== null && idle.length > 0 && (
          <button type="button" className="tst-shelf" aria-expanded={idleShown} onClick={() => setIdleShown(!idleShown)}>
            <Icon name="chevron" size={14} />
            {plural(idle.length, "organization", "organizations")} used nothing {said}
          </button>
        )}
        {idleShown &&
          idle.map((one) => (
            <div key={one.id} className="tst-row bxu-idle">
              <Link to={`/box/orgs/${encodeURIComponent(one.slug)}`} className="tst-row-main bxu-row">
                <Mark name={one.name || one.slug} />
                <span className="tst-row-words">
                  <span className="tst-row-name">
                    <span className="dash-clip">{one.name}</span>
                    <span className="tst-tag">{one.slug}</span>
                  </span>
                  <span className="tst-row-under">Nothing metered {said}.</span>
                </span>
              </Link>
            </div>
          ))}
      </section>

      {rows !== null && !through && (
        <button type="button" className="app-button bxu-more" disabled={reading || next === null} onClick={() => next !== null && setFrom(next)}>
          {reading ? `Reading… ${count(rows.length)} rows` : `Read on: ${count(rows.length)} rows read, and there are more`}
        </button>
      )}
    </div>
  );
}

/** Nothing is asked of the gateway for a person who does not run the deployment. */
export function BoxUsagePage(): ReactNode {
  const { whose } = useOrg();
  return (
    <>
      <PageHead />
      {whose !== null && (whose.operator === true ? <BoxUsage /> : <p className="dash-quiet">This page is the operator's: the person who runs this deployment.</p>)}
    </>
  );
}
