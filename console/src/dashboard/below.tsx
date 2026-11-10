/** Under the dashboard's graphs: every agent and app with its numbers, the alerts, the calls worth opening first, and the latest ones. */

import type { ReactNode } from "react";
import { Link } from "react-router";

import { elapsed, isSimulated, whoOn } from "@pinecall/core/calls";
import type { SessionFlag, SessionLine } from "@pinecall/core/wire/rest";
import { Avatar, AvatarOf } from "../apps/avatar";
import { saidOf } from "../apps/fold";
import { ago, count, money, percent } from "../lib/format";
import type { Insights } from "../lib/insights";
import type { Alert } from "../monitors/door";
import { alertOf } from "../monitors/words";
import { spendTotal } from "../observability/fold";
import { Icon } from "../shell/icons";
import { leftAt, useFleet } from "./fleet";

const SHOWN = 6;
const LISTED = 8;

const FLAG_SAID: Readonly<Record<SessionFlag, { said: string; mood: "bad" | "warn" }>> = {
  low_score: { said: "A judge said no", mood: "bad" },
  escalated: { said: "A person took part", mood: "warn" },
  promise: { said: "A promise no tool recorded", mood: "warn" },
};

function callerOf(line: SessionLine): string {
  return isSimulated(line) ? "Simulated caller" : whoOn(line, (id) => `Visitor ${id}`);
}

function Head({ title, to }: { title: string; to?: string }): ReactNode {
  return (
    <div className="dash-card-top">
      <span className="dash-eyebrow">{title}</span>
      {to !== undefined && (
        <Link to={to} className="dash-more">
          See all
        </Link>
      )}
    </div>
  );
}

/** Every agent and app with how it stands, the ones the window counted calls for first; a name that only has calls is listed too. */
function AgentsAndApps({ counted }: { counted: Insights | null }): ReactNode {
  const { studio, code } = useFleet();
  const known = [...studio.map((app) => ({ app, kind: "studio" as const })), ...code.map((app) => ({ app, kind: "code" as const }))];
  const of = new Map((counted?.agents ?? []).map((one) => [one.slug, one]));
  const gone = [...of.keys()].filter((slug) => !known.some((one) => one.app.name === slug)).map((slug) => ({ app: { name: slug, hosted: null, held: null }, kind: "code" as const, gone: true }));
  const rows = [...known.map((one) => ({ ...one, gone: false })), ...gone].sort((a, b) => (of.get(b.app.name)?.calls ?? 0) - (of.get(a.app.name)?.calls ?? 0) || a.app.name.localeCompare(b.app.name));
  return (
    <section className="dash-card" aria-label="Agents and apps">
      <Head title="Agents and apps" to="/agents" />
      {rows.length === 0 ? (
        <p className="dash-quiet">No agent yet. Build one in Studio, or run pinecall deploy in an app's folder.</p>
      ) : (
        <div className="dash-rows">
          <div className="dash-agent dash-row-head">
            <span />
            <span>Name</span>
            <span className="dash-num">Calls</span>
            <span className="dash-num">Held</span>
            <span className="dash-num">Spend</span>
          </div>
          {rows.slice(0, LISTED).map(({ app, kind, gone: left }) => {
            const said = saidOf(app);
            const numbers = of.get(app.name);
            return (
              <Link key={`${kind}:${app.name}`} to={`/${kind === "code" ? "apps" : "agents"}/${encodeURIComponent(app.name)}`} className="dash-agent dash-row">
                <Avatar kind={kind} name={app.name} size={28} />
                <span className="dash-agent-words">
                  <span className="dash-agent-name">{app.name}</span>
                  <span className="dash-agent-state dash-quiet dash-clip">
                    {!left && <span className={`app-dot app-dot-${said.mood}`} aria-hidden="true" />}
                    {left ? "Not connected now" : `${said.state}, ${kind === "studio" ? "agent" : "app"}`}
                  </span>
                </span>
                <span className="dash-num">{numbers === undefined ? "—" : count(numbers.calls)}</span>
                <span className="dash-num dash-quiet">{numbers?.score == null ? "—" : percent(numbers.score)}</span>
                <span className="dash-num dash-quiet">{numbers === undefined ? "—" : money(spendTotal(numbers.spend))}</span>
              </Link>
            );
          })}
        </div>
      )}
    </section>
  );
}

function Alerts({ alerts }: { alerts: readonly Alert[] | null }): ReactNode {
  return (
    <section className="dash-card" aria-label="Alerts">
      <Head title="Alerts" to="/monitors" />
      {alerts === null || alerts.length === 0 ? (
        <p className="dash-quiet">{alerts === null ? "Reading…" : "Nothing has needed attention. A monitor that fires, a vendor that fails a call or a quota that runs out shows up here."}</p>
      ) : (
        <div className="dash-rows">
          {alerts.slice(0, SHOWN).map((one) => {
            const said = alertOf(one);
            return (
              <Link key={one.id} to="/monitors" className="dash-look dash-row">
                <span className="dash-alert-mark" aria-hidden="true">
                  <Icon name="bell" size={13} />
                </span>
                <span className="dash-look-words dash-look-fill">
                  <span className="dash-clip">{said.title}</span>
                  <span className="dash-look-why dash-quiet dash-clip">{[said.about, one.agent].filter((part) => part !== null && part !== "").join(", ") || "The whole organization"}</span>
                </span>
                <span className="dash-quiet dash-num">{ago(leftAt(one))}</span>
              </Link>
            );
          })}
        </div>
      )}
    </section>
  );
}

function NeedsALook({ lines }: { lines: readonly SessionLine[] }): ReactNode {
  const worth = lines.filter((line) => (line.flags?.length ?? 0) > 0).slice(0, SHOWN);
  return (
    <section className="dash-card" aria-label="Needs a look">
      <Head title="Needs a look" to="/cases" />
      {worth.length === 0 ? (
        <p className="dash-quiet">Nothing flagged in the latest calls.</p>
      ) : (
        <div className="dash-rows">
          {worth.map((line) => {
            const flag = FLAG_SAID[line.flags?.[0] ?? "escalated"];
            return (
              <Link key={line.call} to={`/calls/${encodeURIComponent(line.call)}`} className="dash-look dash-row">
                <AvatarOf name={line.agent} size={24} />
                <span className="dash-look-words dash-look-fill">
                  <span className="dash-clip">{callerOf(line)}</span>
                  <span className={`dash-look-why dash-clip dash-mood-${flag.mood}`}>
                    {flag.said}, {line.agent}
                  </span>
                </span>
                <span className="dash-quiet dash-num">{ago(line.started_at)}</span>
              </Link>
            );
          })}
        </div>
      )}
    </section>
  );
}

function LatestCalls({ lines }: { lines: readonly SessionLine[] }): ReactNode {
  return (
    <section className="dash-card" aria-label="Latest calls">
      <Head title="Latest calls" to="/calls" />
      {lines.length === 0 ? (
        <p className="dash-quiet">No call yet. The first one shows up here the moment it starts.</p>
      ) : (
        <div className="dash-rows">
          {lines.slice(0, SHOWN).map((line) => (
            <Link key={line.call} to={`/calls/${encodeURIComponent(line.call)}`} className="dash-look dash-row">
              <AvatarOf name={line.agent} size={24} />
              <span className="dash-look-words dash-look-fill">
                <span className="dash-clip">{callerOf(line)}</span>
                <span className="dash-look-why dash-quiet dash-clip">{[line.agent, line.channel].filter((part) => part != null).join(", ")}</span>
              </span>
              <span className="dash-num dash-quiet">{line.live ? <span className="dash-mood-good">Live, {elapsed(line.started_at)}</span> : ago(line.started_at)}</span>
            </Link>
          ))}
        </div>
      )}
    </section>
  );
}

export function Below({ counted, lines, alerts }: { counted: Insights | null; lines: readonly SessionLine[]; alerts: readonly Alert[] | null }): ReactNode {
  return (
    <>
      <div className="dash-lead">
        <AgentsAndApps counted={counted} />
        <Alerts alerts={alerts} />
      </div>
      <div className="dash-pair dash-stretch">
        <NeedsALook lines={lines} />
        <LatestCalls lines={lines} />
      </div>
    </>
  );
}
