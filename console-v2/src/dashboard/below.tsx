/** Under the dashboard's graphs: the busiest agents of the window, the calls worth opening first, and the latest ones. */

import type { ReactNode } from "react";
import { Link } from "react-router";

import { elapsed, isSimulated, whoOn } from "@pinecall/core/calls";
import type { SessionFlag, SessionLine } from "@pinecall/core/wire/rest";
import { ago, count, percent } from "../lib/format";
import type { Insights } from "../lib/insights";

const SHOWN = 6;

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

function BusiestAgents({ counted, code }: { counted: Insights | null; code: ReadonlySet<string> }): ReactNode {
  const agents = [...(counted?.agents ?? [])].filter((one) => one.calls > 0).sort((a, b) => b.calls - a.calls).slice(0, SHOWN);
  const most = agents[0]?.calls ?? 1;
  return (
    <section className="dash-card" aria-label="Busiest agents">
      <Head title="Busiest agents" to="/agents" />
      {agents.length === 0 ? (
        <p className="dash-quiet">No agent took a call in these days.</p>
      ) : (
        <div className="dash-rows">
          {agents.map((agent) => (
            <Link key={agent.slug} to={`/${code.has(agent.slug) ? "apps" : "agents"}/${encodeURIComponent(agent.slug)}`} className="dash-busy dash-row">
              <span className="dash-clip">{agent.slug}</span>
              <span className="dash-num">{count(agent.calls)}</span>
              <span className="dash-num dash-quiet">{agent.score === null ? "—" : percent(agent.score)}</span>
              <span className="dash-busy-track" aria-hidden="true">
                <span style={{ width: `${(agent.calls / most) * 100}%` }} />
              </span>
            </Link>
          ))}
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
              <div key={line.call} className="dash-look dash-row">
                <span className="dash-look-words">
                  <span className="dash-clip">{callerOf(line)}</span>
                  <span className={`dash-look-why dash-clip dash-mood-${flag.mood}`}>{flag.said}</span>
                </span>
                <span className="dash-quiet dash-num">{ago(line.started_at)}</span>
              </div>
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
            <div key={line.call} className="dash-look dash-row">
              <span className="dash-look-words">
                <span className="dash-clip">{callerOf(line)}</span>
                <span className="dash-look-why dash-quiet dash-clip">{line.agent}</span>
              </span>
              <span className="dash-num dash-quiet">{line.live ? <span className="dash-mood-good">Live, {elapsed(line.started_at)}</span> : ago(line.started_at)}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

export function Below({ counted, lines, code }: { counted: Insights | null; lines: readonly SessionLine[]; code: ReadonlySet<string> }): ReactNode {
  return (
    <div className="dash-three">
      <BusiestAgents counted={counted} code={code} />
      <NeedsALook lines={lines} />
      <LatestCalls lines={lines} />
    </div>
  );
}
