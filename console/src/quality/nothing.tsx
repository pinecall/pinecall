/** What Quality draws when no call of the window got a verdict: one card saying so, and why when no judge is on. */

import type { ReactNode } from "react";
import { Link } from "react-router";

import type { WindowDays } from "../lib/insights";
import { windowSaid } from "./window";

/** `judging` is whether a judge is on, null until the judges are read; `onWiden` is null on the widest window. */
export function NothingJudged({ days, judging, calls, onWiden }: { days: WindowDays; judging: boolean | null; /** The calls of whoever is in view. */ calls: string; onWiden: (() => void) | null }): ReactNode {
  const unruled = judging === false;
  return (
    <section className="dash-card ql-none" aria-label="Nothing judged">
      <h2 className="app-name">{unruled ? "No rule is checked yet" : `Nothing judged in ${windowSaid(days)}`}</h2>
      <p className="dash-quiet ql-none-words">
        {unruled
          ? "A judge reads every call that ends and checks it against one rule written in plain words; once one is on, every call gets a verdict and this page counts them."
          : "Your judges are on, so every call that ends from now on gets a verdict, and this page shows how many kept every rule and which broke one."}
      </p>
      <div className="ql-none-moves">
        {!unruled && onWiden !== null && (
          <button type="button" className="ql-solid" onClick={onWiden}>
            See the last 30 days
          </button>
        )}
        {!unruled && onWiden === null && (
          <Link to="/simulations" className="ql-solid ql-button-link">
            Simulate a call
          </Link>
        )}
        <Link to={calls} className="app-button ql-button-link">
          Open calls
        </Link>
      </div>
    </section>
  );
}
