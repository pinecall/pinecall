/** Calls: the org's newest, a live one first as the gateway orders them. */

import type { ReactNode } from "react";

import { elapsed, isSimulated, whoOn } from "@pinecall/core/calls";
import type { SessionLine } from "@pinecall/core/wire/rest";
import { ago, lengthOf } from "../lib/format";
import { useOrg } from "../lib/org";
import "./dashboard.css";

function endOf(line: SessionLine): string {
  return line.end_reason === null ? "" : line.end_reason.replace(/_/g, " ");
}

export function CallsPage(): ReactNode {
  const { lines } = useOrg();
  return (
    <section className="dash-card" aria-label="Latest calls">
      {lines.length === 0 ? (
        <p className="dash-quiet">No call yet. The first one shows up here the moment it starts.</p>
      ) : (
        <div className="dash-rows">
          <div className="dash-call dash-row-head">
            <span>Caller</span>
            <span>Agent</span>
            <span>Channel</span>
            <span>Ended</span>
            <span className="dash-num">Length</span>
            <span className="dash-num">When</span>
          </div>
          {lines.map((line) => (
            <div key={line.call} className="dash-call dash-row">
              <span className="dash-call-who">
                {isSimulated(line) ? <span className="dash-tag">Simulated caller</span> : whoOn(line, (id) => `Visitor ${id}`)}
              </span>
              <span className="dash-quiet dash-clip">{line.agent}</span>
              <span className="dash-quiet dash-first">{line.channel ?? "—"}</span>
              <span className="dash-quiet dash-clip dash-first">{line.live ? <span className="dash-mood-good">Live, {elapsed(line.started_at)}</span> : endOf(line)}</span>
              <span className="dash-num dash-quiet">{line.live ? "" : lengthOf(line.started_at, line.ended_at)}</span>
              <span className="dash-num dash-quiet">{ago(line.started_at)}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
