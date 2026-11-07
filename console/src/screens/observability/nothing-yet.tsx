/** Nothing yet: what the screen draws in place of its cards when the window holds no timed turn, no tool run and no verdict. */

import type { ReactNode } from "react";

import { windowSaid, type WindowDays } from "../../lib/insights";
import { rowAt, whoseIs } from "../../lib/harness";
import { Button, ButtonLink, Icon, Nothing } from "../../ui";

// A sketch of the chart the page will draw, so the empty page says what is coming rather than looking broken.
const GHOST = "M0 70 C 40 66, 60 40, 100 46 S 160 72, 200 58 S 270 24, 320 34 S 380 52, 420 40";
const PARTS = [
  { key: "hears", width: 22 },
  { key: "thinks", width: 38 },
  { key: "tools", width: 12 },
  { key: "speaks", width: 28 },
] as const;

function Sketch(): ReactNode {
  return (
    <>
      <svg className="obs-none-art" viewBox="0 0 420 90" preserveAspectRatio="none">
        <line className="obs-none-rule" x1="0" x2="420" y1="22" y2="22" />
        <line className="obs-none-rule" x1="0" x2="420" y1="52" y2="52" />
        <line className="obs-none-rule" x1="0" x2="420" y1="82" y2="82" />
        <path className="obs-none-line" d={GHOST} />
      </svg>
      <div className="obs-none-bar">
        {PARTS.map((part) => (
          <span key={part.key} className={`obs-split-part obs-part-${part.key}`} style={{ width: `${part.width}%` }} />
        ))}
      </div>
    </>
  );
}

export function NothingYet({ range, agent, calls, onWiden }: { range: WindowDays; agent: string; calls: number; onWiden: (() => void) | null }): ReactNode {
  return (
    <Nothing
      art={<Sketch />}
      title={`Nothing to observe in ${windowSaid(range)}`}
      actions={
        <>
          {onWiden !== null ? (
            <Button kind="primary" onClick={onWiden}>
              See the last 30 days
            </Button>
          ) : (
            <ButtonLink kind="primary" to={rowAt(agent, "simulations")}>
              <Icon name="headphones" size={14} />
              Simulate a call
            </ButtonLink>
          )}
          <ButtonLink to={rowAt(agent, "calls")}>
            <Icon name="list" size={14} />
            Open calls
          </ButtonLink>
        </>
      }
    >
      This page fills in as {whoseIs(agent)} {agent === "" ? "answer" : "answers"} calls: how long a caller waits for the first word and where that time goes, how calls end, what the judges hold, which tools fail and what it all costs.
      {calls > 0 && ` ${calls === 1 ? "One call came in" : `${calls} calls came in`}, but none got as far as a turn.`}
    </Nothing>
  );
}
