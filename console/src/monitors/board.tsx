/** The monitors and the alerts of one agent, or of the whole organization, a tab each: what is watched and how each stands, what needed attention, and the way to watch one more. */

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { ConfirmButton } from "../apps/confirm";
import { ago } from "../lib/format";
import { useOrg } from "../lib/org";
import { useAgentPage } from "../numbers/number-view";
import { Icon, type IconName } from "../shell/icons";
import { Field } from "../ui/setting";
import { SidePanel } from "../ui/side-panel";
import { dropMonitor, readAlerts, readMonitors, type Alert, type Monitor } from "./door";
import { NewMonitorPanel } from "./new-monitor";
import { alertOf, factsOf, ruleOf, standingOf } from "./words";
import "../dashboard/dashboard.css";
import "../configure/configure.css";
import "../test/test.css";
import "./monitors.css";

// How many alerts a section draws before it offers the rest.
const A_FEW = 12;

type Tab = "monitors" | "alerts";
const TABS: readonly { tab: Tab; name: string }[] = [
  { tab: "monitors", name: "Monitors" },
  { tab: "alerts", name: "Alerts" },
];

type Open = { panel: "new" } | { panel: "monitor"; id: string } | { panel: "alert"; id: string };

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

const whenOf = (alert: Alert): string => ago(Date.parse(alert.at) / 1000);

function MonitorPanel({ monitor, fired, onRemoved, onAlert, onClose }: { monitor: Monitor; fired: readonly Alert[]; onRemoved: () => void; onAlert: (id: string) => void; onClose: () => void }): ReactNode {
  const credentials = useCredentials();
  const [refused, setRefused] = useState<string | null>(null);
  const standing = standingOf(monitor);
  return (
    <SidePanel
      title={monitor.name}
      icon="monitors"
      about={`Fires when ${ruleOf(monitor).replace(/^./, (first) => first.toLowerCase())}, for ${monitor.agent === null ? "every agent's calls" : `${monitor.agent}'s calls`}.`}
      onClose={onClose}
      footer={
        <>
          {refused !== null && <p className="cfg-refused">{refused}</p>}
          <div className="cfg-dialog-foot">
            <ConfirmButton label="Stop watching" asks="Stop watching it?" danger onConfirm={() => void dropMonitor(credentials, monitor.id).then(onRemoved, (failed: unknown) => setRefused(saidBy(failed)))} />
          </div>
        </>
      }
    >
      <div className={`tst-last tst-last-${standing.mood}`}>
        <span className="tst-last-top">
          <b>{standing.mood === "broke" ? "Over the line" : standing.mood === "held" ? "Back inside the line" : "Inside the line"}</b>
          <span className="dash-quiet">{standing.said}</span>
        </span>
      </div>
      <Field label="Every time it fired">
        {fired.length === 0 ? (
          <p className="dash-quiet">It has not fired in the ninety days alerts are kept.</p>
        ) : (
          <div className="mon-fired">
            {fired.map((one) => (
              <button key={one.id} type="button" className="mon-fired-row" onClick={() => onAlert(one.id)}>
                <span>{alertOf(one).about}</span>
                <span className="dash-quiet">
                  {one.agent ?? "every agent"}, {whenOf(one)}
                </span>
              </button>
            ))}
          </div>
        )}
      </Field>
    </SidePanel>
  );
}

function AlertPanel({ alert, onClose }: { alert: Alert; onClose: () => void }): ReactNode {
  const pageOf = useAgentPage();
  const said = alertOf(alert);
  const call = typeof alert.data["call"] === "string" ? alert.data["call"] : null;
  return (
    <SidePanel title={said.title} icon="bell" about={`${whenOf(alert)}${alert.agent === null ? "" : `, on ${alert.agent}`}. ${alert.mailed ? "The org's admins were mailed." : "Nobody was mailed."}`} onClose={onClose}>
      <dl className="tst-facts">
        {factsOf(alert).map((fact) => (
          <div key={fact.name}>
            <dt>{fact.name}</dt>
            <dd>{fact.value}</dd>
          </div>
        ))}
      </dl>
      <div className="mon-links">
        {call !== null && (
          <Link to={`/calls/${encodeURIComponent(call)}`} className="app-button">
            Open the call
          </Link>
        )}
        {alert.agent !== null && (
          <Link to={pageOf(alert.agent)} className="app-button">
            Open {alert.agent}
          </Link>
        )}
      </div>
    </SidePanel>
  );
}

/** `agent` draws that agent's own monitors and the alerts on its calls; null, the organization's, every agent's among them. */
export function MonitorsBoard({ agent }: { agent: string | null }): ReactNode {
  const credentials = useCredentials();
  const { agents } = useOrg();
  const pageOf = useAgentPage();
  const [monitors, setMonitors] = useState<Monitor[] | null>(null);
  const [alerts, setAlerts] = useState<Alert[] | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  const [open, setOpen] = useState<Open | null>(null);
  const [all, setAll] = useState(false);
  const [tab, setTab] = useState<Tab>("monitors");
  const close = useCallback(() => setOpen(null), []);

  useEffect(() => {
    readMonitors(credentials).then(setMonitors, (failed: unknown) => (setMonitors([]), setRefused(saidBy(failed))));
    // A key that may not read alerts still reads and writes monitors.
    readAlerts(credentials).then(setAlerts, () => setAlerts([]));
  }, [credentials]);

  const mine = useMemo(() => (monitors ?? []).filter((one) => agent === null || one.agent === agent), [monitors, agent]);
  // What watches every agent watches this one too: said under its own, and changed on the Monitors page.
  const everyones = useMemo(() => (agent === null ? [] : (monitors ?? []).filter((one) => one.agent === null)), [monitors, agent]);
  const told = useMemo(() => (alerts ?? []).filter((one) => agent === null || one.agent === agent), [alerts, agent]);
  const firing = mine.filter((one) => standingOf(one).mood === "broke").length;
  const shown = all ? told : told.slice(0, A_FEW);
  const openMonitor = open?.panel === "monitor" ? (monitors ?? []).find((one) => one.id === open.id) : undefined;
  const openAlert = open?.panel === "alert" ? (alerts ?? []).find((one) => one.id === open.id) : undefined;

  const row = (one: Monitor, own: boolean): ReactNode => {
    const standing = standingOf(one);
    return (
      <div key={one.id} className={openMonitor?.id === one.id ? "tst-row tst-row-on" : "tst-row"}>
        <button type="button" className="tst-row-main" onClick={() => setOpen({ panel: "monitor", id: one.id })}>
          <span className="tst-mark" aria-hidden="true">
            <Icon name="monitors" size={14} />
          </span>
          <span className="tst-row-words">
            <span className="tst-row-name">
              <span className="dash-clip">{one.name}</span>
              {agent === null && <span className="tst-tag">{one.agent ?? "every agent"}</span>}
              {!own && <span className="tst-tag">every agent</span>}
            </span>
            <span className="tst-row-under dash-clip">{ruleOf(one)}</span>
          </span>
          <span className={`tst-status mon-status tst-status-${standing.mood}`}>{standing.said}</span>
        </button>
      </div>
    );
  };

  return (
    <div className="tst mon">
      {refused !== null && (
        <p className="cfg-refused" role="alert">
          {refused}
        </p>
      )}

      {/* The rule and what it told are two lists, never one: a tab each. */}
      <div className="dash-switch mon-tabs" role="tablist" aria-label="Monitors or alerts">
        {TABS.map((one) => (
          <button key={one.tab} type="button" role="tab" aria-selected={tab === one.tab} className={tab === one.tab ? "dash-switch-on" : ""} onClick={() => setTab(one.tab)}>
            {one.name}
            {one.tab === "alerts" && told.length > 0 && <span className="mon-tab-count">{told.length === 200 ? "200+" : told.length}</span>}
          </button>
        ))}
      </div>

      {tab === "monitors" && (
        <section className="tst-list mon-tone-pink" aria-label="Monitors">
          <Head icon="monitors" title="Monitors" about={agent === null ? "The rules: a number of the calls watched over a window, and the line it must not cross. One that crosses it leaves an alert." : `The rules: a number of ${agent}'s calls watched over a window, and the line it must not cross. One that crosses it leaves an alert.`}>
            {mine.length > 0 && <span className="tst-head-stands">{firing === 0 ? "None over its line" : `${firing} over ${firing === 1 ? "its" : "their"} line`}</span>}
            <button type="button" className="cfg-save tst-action" onClick={() => setOpen({ panel: "new" })}>
              <Icon name="plus" size={12} />
              New monitor
            </button>
          </Head>
          {monitors === null && <p className="dash-quiet tst-none">Reading…</p>}
          {mine.map((one) => row(one, true))}
          {monitors !== null && mine.length === 0 && <p className="dash-quiet tst-none">{agent === null ? "Nothing is watched yet." : `Nothing watches ${agent} alone yet.`}</p>}
          {everyones.length > 0 && (
            <>
              <span className="mon-also">Also watching it, with every other agent</span>
              {everyones.map((one) => row(one, false))}
            </>
          )}
        </section>
      )}

      {tab === "alerts" && (
        <section className="tst-list tst-tone-gold" aria-label="Alerts">
          <Head icon="bell" title="Alerts" about={agent === null ? "What needed attention: a monitor fired, a vendor failed a call, a quota ran out. Kept ninety days." : `What needed attention on ${agent}'s calls. Kept ninety days.`}>
            {told.length > 0 && <span className="tst-head-stands">{told.length === 200 ? "200 or more" : told.length}</span>}
          </Head>
          {alerts === null && <p className="dash-quiet tst-none">Reading…</p>}
          {shown.map((one) => {
            const said = alertOf(one);
            return (
              <div key={one.id} className={openAlert?.id === one.id ? "tst-row tst-row-on" : "tst-row"}>
                <button type="button" className="tst-row-main" onClick={() => setOpen({ panel: "alert", id: one.id })}>
                  <span className="tst-mark" aria-hidden="true">
                    <Icon name="bell" size={14} />
                  </span>
                  <span className="tst-row-words">
                    <span className="tst-row-name">
                      <span className="dash-clip">{said.title}</span>
                      {agent === null && one.agent !== null && <span className="tst-tag">{one.agent}</span>}
                    </span>
                    <span className="tst-row-under dash-clip">{said.about}</span>
                  </span>
                  <span className="tst-row-when">{whenOf(one)}</span>
                </button>
              </div>
            );
          })}
          {alerts !== null && told.length === 0 && <p className="dash-quiet tst-none">Nothing needed attention.</p>}
          {told.length > A_FEW && !all && (
            <button type="button" className="tst-shelf" onClick={() => setAll(true)}>
              Show all {told.length}
            </button>
          )}
        </section>
      )}

      {open?.panel === "new" && (
        <NewMonitorPanel
          agent={agent}
          agents={agents.map((one) => one.slug)}
          onSaved={(kept) => {
            setMonitors((was) => [...(was ?? []), kept]);
            setOpen({ panel: "monitor", id: kept.id });
          }}
          onClose={close}
        />
      )}
      {openMonitor !== undefined && <MonitorPanel key={openMonitor.id} monitor={openMonitor} fired={(alerts ?? []).filter((one) => one.data["monitor"] === openMonitor.id)} onRemoved={() => (setMonitors((was) => (was ?? []).filter((one) => one.id !== openMonitor.id)), close())} onAlert={(id) => setOpen({ panel: "alert", id })} onClose={close} />}
      {openAlert !== undefined && <AlertPanel key={openAlert.id} alert={openAlert} onClose={close} />}
      {agent !== null && everyones.length > 0 && (
        <Link to={pageOf(agent).replace(/^\/(agents|apps)\/.*/, "/monitors")} className="tst-link mon-org">
          Every monitor of the organization
        </Link>
      )}
    </div>
  );
}
