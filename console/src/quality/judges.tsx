/** The agents with how each one's calls held, the judges with how each held over the calls read, a row each that opens its detail, and beside them the calls that broke a rule, each a link into the call. */

import type { ReactNode } from "react";
import { Link } from "react-router";

import { whoOn } from "@pinecall/core/calls";
import { AvatarOf } from "../apps/avatar";
import { Face } from "../calls/face";
import { Creature } from "../judges/creature";
import { dayAndTime, webVisitor } from "../calls/format";
import { count, percent } from "../lib/format";
import type { Insights } from "../lib/insights";
import { toneOf, type BrokenCall, type Rule } from "./rules";

function JudgeRow({ rule, on, onOpen }: { rule: Rule; on: boolean; onOpen: () => void }): ReactNode {
  const share = rule.settled === 0 ? null : rule.held / rule.settled;
  const broke = rule.settled - rule.held;
  return (
    <button type="button" className={on ? "dash-row ql-row ql-row-on" : "dash-row ql-row"} aria-pressed={on} onClick={onOpen}>
      <Creature name={rule.name} size={30} />
      <span className="ql-row-main">
        <span className="ql-row-title dash-clip">{rule.said}</span>
        <span className="ql-row-under dash-clip">
          {rule.name} · {rule.settled} judged
        </span>
      </span>
      {share !== null && (
        <span className="ql-track" aria-hidden="true">
          <span className={`ql-fill-${toneOf(share)}`} style={{ width: `${share * 100}%` }} />
        </span>
      )}
      <span className={share === null ? "ql-pct dash-quiet" : `ql-pct ql-tone-${toneOf(share)}`}>{share === null ? "—" : percent(share)}</span>
      <span className={broke > 0 ? "ql-broke ql-tone-bad" : "ql-broke"}>{broke > 0 ? `${broke} broke` : "None broke"}</span>
    </button>
  );
}

/** How each agent held with the judges in the window, the lowest first; a tile narrows the page to that agent. */
export function ByAgent({ agents, onPick }: { agents: Insights["agents"]; onPick: (agent: string) => void }): ReactNode {
  const rows = agents.filter((one) => one.score !== null).sort((one, other) => (one.score ?? 0) - (other.score ?? 0) || other.calls - one.calls);
  return (
    <section className="dash-card" aria-label="By agent">
      <div className="dash-card-top ql-card-top">
        <span className="dash-eyebrow">By agent</span>
        <span className="dash-quiet dash-clip">How each one held with the judges, the lowest first. Pick one to see only its calls</span>
      </div>
      <div className="ql-agents">
        {rows.map((one) => {
          const share = one.score ?? 0;
          return (
            <button key={one.slug} type="button" className="dash-part ql-agent" onClick={() => onPick(one.slug)}>
              <span className="ql-agent-top">
                <AvatarOf name={one.slug} size={28} />
                <span className="ql-row-main">
                  <span className="ql-row-title dash-clip">{one.slug}</span>
                  <span className="ql-row-under dash-clip">
                    {count(one.calls)} {one.calls === 1 ? "call" : "calls"}
                  </span>
                </span>
                <span className={`ql-agent-pct ql-tone-${toneOf(share)}`}>{percent(share)}</span>
              </span>
              <span className="ql-track ql-track-wide" aria-hidden="true">
                <span className={`ql-fill-${toneOf(share)}`} style={{ width: `${share * 100}%` }} />
              </span>
            </button>
          );
        })}
      </div>
    </section>
  );
}

export function Judges({ rules, read, open, onOpen }: { rules: readonly Rule[]; /** How many judged calls the rates are over. */ read: number; open: string | null; onOpen: (name: string) => void }): ReactNode {
  return (
    <section className="dash-card ql-card" aria-label="Judges">
      <div className="dash-card-top ql-card-top">
        <span className="dash-eyebrow">Judges</span>
        <span className="dash-quiet dash-clip">{read === 0 ? "No judged call read yet" : `How each held over the newest ${read} judged ${read === 1 ? "call" : "calls"}`}</span>
      </div>
      {rules.length === 0 ? (
        <p className="dash-quiet">No judge is on, so the calls are held to no rule yet.</p>
      ) : (
        <div className="dash-rows">
          {rules.map((rule) => (
            <JudgeRow key={rule.name} rule={rule} on={rule.name === open} onOpen={() => onOpen(rule.name)} />
          ))}
        </div>
      )}
    </section>
  );
}

function BrokenRow({ call }: { call: BrokenCall }): ReactNode {
  const line = call.row.line;
  const who = whoOn(line, webVisitor);
  const first = call.broke[0];
  return (
    <Link to={`/calls/${encodeURIComponent(line.call)}`} className="dash-row ql-row">
      <Face name={who} />
      <span className="ql-row-main">
        <span className="ql-row-title dash-clip">{who}</span>
        <span className="ql-row-under dash-clip">{first?.reason ?? ""}</span>
      </span>
      <span className="ql-tag dash-clip">{call.broke.length === 1 ? first?.name : `${call.broke.length} rules`}</span>
      <span className="ql-when ql-when-worn">
        <AvatarOf name={line.agent} size={18} />
        {line.agent} · {dayAndTime(line.started_at)}
      </span>
    </Link>
  );
}

export function BrokenCalls({ calls, to }: { calls: readonly BrokenCall[]; /** Every call that broke, in Calls. */ to: string }): ReactNode {
  return (
    <section className="dash-card ql-card" aria-label="Calls that broke a rule">
      <div className="dash-card-top ql-card-top">
        <span className="dash-eyebrow">Calls that broke a rule</span>
        <Link to={to} className="dash-more">
          See them in Calls
        </Link>
      </div>
      {calls.length === 0 ? (
        <p className="dash-quiet">Every rule held on the calls read.</p>
      ) : (
        <div className="dash-rows">
          {calls.map((call) => (
            <BrokenRow key={call.row.line.call} call={call} />
          ))}
        </div>
      )}
    </section>
  );
}
