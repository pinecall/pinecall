/** Finished-call summary: key facts, final summary sentence, and cost. */

import { type Cost } from "@pinecall/core/wire/defs";
import { type State } from "@pinecall/core/wire/state";
import type { ReactNode } from "react";

import { dayAndTime, duration, usd } from "../../../lib/format";
import { Card, CardHead, Stat, Stats } from "../../../ui";

/** One small card per fact, all read from the log. */
export function Facts({ state, events }: { state: State; events: number }): ReactNode {
  return (
    <div className="over-facts">
      <Stats min={130}>
        <Stat size="fact" label="Agent" value={state.agent} />
        <Stat size="fact" label="Channel" value={state.direction === "outbound" ? `${state.channel ?? "—"} · outbound` : (state.channel ?? "—")} />
        <Stat size="fact" label="Started" value={dayAndTime(state.started_at)} />
        <Stat size="fact" label="Duration" value={state.ended_at === null ? "still going" : duration(state)} />
        <Stat size="fact" label="Ended" value={state.end_reason === null ? "not yet" : state.end_reason.replace(/_/g, " ")} />
        <Stat size="fact" label="Cost" value={usd(state.cost?.usd)} />
        <Stat size="fact" label="Turns · events" value={`${state.turns.length} · ${events}`} />
      </Stats>
    </div>
  );
}

/** The call's summary sentence. */
export function Outcome({ state }: { state: State }): ReactNode {
  return (
    <Card pad>
      <div className="over-outcome-label">Outcome</div>
      <div className="over-outcome">{state.outcome ?? (state.end_reason === null ? "The call is still going." : "The call left no outcome sentence.")}</div>
    </Card>
  );
}

/** Cost per model and total. */
export function CostCard({ cost }: { cost: Cost }): ReactNode {
  return (
    <Card>
      <CardHead title="Cost">
        <span className="over-total">{usd(cost.usd)}</span>
      </CardHead>
      <div>
        {/* A call dialled twice bills two legs under one rate: the place tells them apart. */}
        {cost.rows.map((row, place) => (
          <div key={`${place}/${row.provider}/${row.model}/${row.unit}`} className="over-cost">
            <span className="over-cost-model">
              {row.model} <span className="over-cost-kind">· {row.unit.replace(/_/g, " ")}</span>
            </span>
            <span className="over-cost-units">{grouped(row.quantity)}</span>
            <span className="over-cost-usd">{usd(row.usd)}</span>
          </div>
        ))}
      </div>
      {cost.unpriced.length > 0 && (
        <div className="over-note">unpriced: {cost.unpriced.map((row) => `${row.provider}/${row.model}`).join(", ")}</div>
      )}
    </Card>
  );
}

/** Format a count with a space thousands separator: `12 457`. */
function grouped(quantity: number): string {
  const [whole, fraction] = String(Math.round(quantity * 100) / 100).split(".");
  const spaced = (whole ?? "").replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  return fraction === undefined ? spaced : `${spaced}.${fraction}`;
}
