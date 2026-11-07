/** Nothing judged: what Quality draws in place of its cards when no call of the window got a verdict — and why, when no judge is on. */

import type { ReactNode } from "react";

import { rowAt } from "../../lib/harness";
import { windowSaid, type WindowDays } from "../../lib/insights";
import { Button, ButtonLink, Icon, Nothing } from "../../ui";

// The ring the page will draw and a bar a day under it, so the empty page says what is coming.
const DAYS = [46, 62, 54, 78, 70, 88, 82];

function Sketch(): ReactNode {
  return (
    <div className="qly-none-art">
      <svg className="qly-none-ring" viewBox="0 0 36 36">
        <circle cx="18" cy="18" r="15.5" className="qly-none-track" />
        <circle cx="18" cy="18" r="15.5" className="qly-none-fill" pathLength={100} strokeDasharray="82 100" />
      </svg>
      <span className="qly-none-days">
        {DAYS.map((height, at) => (
          <span key={at} className={at === DAYS.length - 1 ? "qly-none-day qly-none-day-now" : "qly-none-day"} style={{ height: `${height}%` }} />
        ))}
      </span>
    </div>
  );
}

/** `judging` is whether a judge is on, null until the judges are read: off, the way forward is writing one. */
export function NothingJudged({ days, agent, judging, onWiden }: { days: WindowDays; agent: string; judging: boolean | null; onWiden: (() => void) | null }): ReactNode {
  const calls = (
    <ButtonLink to={rowAt(agent, "calls")}>
      <Icon name="list" size={14} />
      Open calls
    </ButtonLink>
  );
  if (judging === false) {
    return (
      <Nothing
        art={<Sketch />}
        title="No rule is checked yet"
        actions={
          <>
            <ButtonLink kind="primary" to={rowAt(agent, "judges")}>
              <Icon name="scale" size={14} />
              Write a judge
            </ButtonLink>
            {calls}
          </>
        }
      >
        A judge reads every call that ends and checks it against one rule, written in plain words: “never promises a price”, “books only open slots”, “hands over when asked for a person”. Turn one on and every call from then on gets a verdict — this page counts them, and the calls that broke a rule become cases to fix.
      </Nothing>
    );
  }
  return (
    <Nothing
      art={<Sketch />}
      title={`Nothing judged in ${windowSaid(days)}`}
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
          {calls}
        </>
      }
    >
      Your judges are on: every call that ends from now on is read and gets a verdict. This page then shows the share of calls that kept every rule, the ones that broke one, and the fixes ready for them.
    </Nothing>
  );
}
