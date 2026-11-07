/** No calls yet: what Overview draws in place of its numbers and charts while the last 30 days hold no call. */

import type { ReactNode } from "react";

import { WORLD } from "../../lib/mode";
import { ButtonLink, Icon, Nothing } from "../../ui";

// A sketch of the dashboard to come: three numbers over the calls a day.
const BARS = [22, 34, 28, 46, 40, 58, 52, 64, 48, 70, 62, 78, 66, 84];

function Sketch(): ReactNode {
  return (
    <div className="ovw-none-art">
      <div className="ovw-none-stats">
        {[52, 38, 44].map((width) => (
          <span key={width} className="ovw-none-stat">
            <i style={{ width: `${String(width)}%` }} />
            <b />
          </span>
        ))}
      </div>
      <div className="ovw-none-bars">
        {BARS.map((height, index) => (
          <span key={index} style={{ height: `${String(height)}%` }} />
        ))}
      </div>
    </div>
  );
}

export function NoCalls({ agent }: { agent: string }): ReactNode {
  return (
    <Nothing
      art={<Sketch />}
      title={agent === "" ? "No calls yet" : `${agent} has no calls yet`}
      actions={
        <>
          {WORLD === "sandbox" ? (
            <ButtonLink kind="primary" to="/simulations">
              <Icon name="headphones" size={14} />
              Simulate a call
            </ButtonLink>
          ) : (
            <ButtonLink kind="primary" to="/numbers">
              <Icon name="phone" size={14} />
              Add a number
            </ButtonLink>
          )}
          <ButtonLink to="/agents">
            <Icon name="bot" size={14} />
            Open Agents
          </ButtonLink>
        </>
      }
    >
      This page fills in with the first call: who is on the line right now, how many calls come in, how they end, what the judges hold and what it costs.
    </Nothing>
  );
}
