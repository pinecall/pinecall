/** Observability: the window at a glance, where a caller's wait goes, the slowest turns, the tools and vendors behind them, the spend, and each number a day at a time, for every agent or one. */

import { useCallback, useMemo, useState, type ReactNode } from "react";

import { utcDay } from "../lib/format";
import { useInsights } from "../lib/insights";
import { useOrg } from "../lib/org";
import { Icon } from "../shell/icons";
import { PageHead } from "../shell/page-head";
import { Select } from "../ui/select";
import { TimeToAnswer } from "./answer";
import { ByAgent, ToolsCard, VendorsCard } from "./breakdowns";
import { DayByDay, SpendCard } from "./days";
import { measured, useMonitors, useOwnVendors, useSeries, useSlowTurns, useTools, type SlowTurn } from "./door";
import { totalsOf } from "./fold";
import { Hero } from "./hero";
import { LiveEvents } from "./live-events";
import { SlowTurnPanel, SlowTurns } from "./slow-turns";
import { TelemetryPanel } from "./telemetry-panel";
import { useOpeningWindow, useWidenedWhenQuiet, WINDOWS, windowSaid } from "./window";
import "../dashboard/dashboard.css";
import "../apps/apps.css";
import "./observability.css";

/** What the side panel holds: one slow turn, or where the traces go. */
type Docked = { turn: SlowTurn } | "traces" | null;

/**
 * Every number is the gateway's count over whole UTC days; a day nobody called is a gap, not a
 * zero. Unless a window was picked the page opens on the week, and on the month when the week
 * holds nothing it draws; a window with nothing in it draws one card saying so.
 */
export function ObservabilityPage(): ReactNode {
  const opening = useOpeningWindow();
  const { days: range, agent } = opening;
  const { agents, lines } = useOrg();
  const [docked, setDocked] = useState<Docked>(null);
  const close = useCallback(() => setDocked(null), []);

  const asked = useMemo(() => ({ days: range, agent }), [range, agent]);
  const earlier = useMemo(() => ({ days: range, agent, day: utcDay(Date.now() / 1000 - range * 86400) }), [range, agent]);
  const answered = useSeries(asked);
  const answeredBefore = useSeries(earlier);
  const read = useInsights(range, agent === "" ? {} : { agent });
  const insights = read?.days === range ? read : null;
  const tools = useTools(asked);
  const slow = useSlowTurns(asked);
  const monitors = useMonitors();
  const own = useOwnVendors();

  const rows = useMemo(() => answered?.series ?? [], [answered]);
  const now = useMemo(() => totalsOf(rows), [rows]);
  const before = useMemo(() => (answeredBefore == null ? null : totalsOf(answeredBefore.series)), [answeredBefore]);
  const quiet = answered == null ? null : !measured(rows);
  const deciding = useWidenedWhenQuiet(opening, quiet);
  const said = windowSaid(range);

  // Calls of agents nobody holds any more happened too: they stay in the list.
  const slugs = useMemo(() => [...new Set([...agents.map((one) => one.slug), ...lines.map((line) => line.agent), ...(agent === "" ? [] : [agent])])].sort(), [agents, lines, agent]);
  const open = docked !== null && docked !== "traces" ? docked.turn : null;

  return (
    <>
      <PageHead>
        {slugs.length > 1 && (
          <div className="ob-pick">
            <Select label="Which agent" value={agent} items={[{ value: "", label: "Every agent" }, ...slugs.map((slug) => ({ value: slug, label: slug }))]} onChange={opening.pickAgent} />
          </div>
        )}
        <div className="dash-switch" role="group" aria-label="Window">
          {WINDOWS.map((one) => (
            <button key={one.days} type="button" aria-pressed={one.days === range} className={one.days === range ? "dash-switch-on" : ""} onClick={() => opening.pick(one.days)}>
              {one.label}
            </button>
          ))}
        </div>
        <button type="button" className={docked === "traces" ? "app-button ob-head-button ob-head-button-on" : "app-button ob-head-button"} aria-pressed={docked === "traces"} onClick={() => setDocked(docked === "traces" ? null : "traces")}>
          <Icon name="wave" size={14} />
          Send traces
        </button>
      </PageHead>

      <div className="ob">
        {answered === null ? (
          <section className="dash-card ob-none" aria-label="Nothing to show">
            <p>This key may not read how calls ran, or this server does not count it yet.</p>
          </section>
        ) : deciding || answered === undefined ? null : quiet === true ? (
          <>
            <section className="dash-card ob-none" aria-label="Nothing to show">
              <p>
                {now.calls === 0
                  ? `Nothing was measured in ${said}: this page fills in as ${agent === "" ? "your agents answer" : `${agent} answers`} calls.`
                  : `${now.calls === 1 ? "One call came in" : `${now.calls} calls came in`} in ${said}, but none got as far as a turn, so there is nothing to measure yet.`}
              </p>
              {range !== 30 && (
                <button type="button" className="cfg-save" onClick={() => opening.pick(30)}>
                  See the last 30 days
                </button>
              )}
            </section>
            <LiveEvents />
          </>
        ) : (
          <>
            <Hero now={now} before={before} days={range} />
            <TimeToAnswer series={answered} tools={tools ?? []} monitors={monitors} agent={agent} />
            <div className="ob-pair">
              {slow != null && <SlowTurns turns={slow} open={open} onOpen={(turn) => setDocked({ turn })} />}
              <LiveEvents />
            </div>
            {/* These are a newer runtime's: a box without them draws the page without the card. */}
            {(tools != null || answered.vendors.length > 0) && (
              <div className="ob-pair">
                {tools != null && <ToolsCard tools={tools} />}
                {answered.vendors.length > 0 && <VendorsCard vendors={answered.vendors} own={own} monitors={monitors} agent={agent} />}
              </div>
            )}
            <SpendCard rows={rows} agents={insights?.agents ?? null} said={said} />
            {agent === "" && insights !== null && insights.agents.length > 0 && <ByAgent agents={insights.agents} said={said} />}
            <h2 className="dash-eyebrow ob-section">A day at a time</h2>
            <DayByDay rows={rows} said={said} />
          </>
        )}
      </div>

      {open !== null && <SlowTurnPanel turn={open} onClose={close} />}
      {docked === "traces" && <TelemetryPanel onClose={close} />}
    </>
  );
}
