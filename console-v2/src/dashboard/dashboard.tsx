/** The home, one page: the harness on top, its judges over the month, then the numbers and graphs of the window picked, and the agents and calls to look at. */

import { useMemo, useState, type ReactNode } from "react";

import { change, percent, utcDay } from "../lib/format";
import { useHarness } from "../lib/harness";
import { useInsights, type WindowDays } from "../lib/insights";
import { useOrg } from "../lib/org";
import { NoticesButton } from "../shell/notices";
import { PageHead } from "../shell/page-head";
import { Below } from "./below";
import { HarnessCards } from "./harness";
import { Overview } from "./overview";
import "./dashboard.css";

const WINDOWS: readonly WindowDays[] = [1, 7, 30];
// The harness is the state of the agents, not of the window picked: a quiet week must not read as nothing judged.
const HARNESS_DAYS: WindowDays = 30;
const WINDOW_UNDER = "pinecall.dashboard-days";

// This tab's preference; where storage is blocked the choice lasts as long as the page.
function keptWindow(): WindowDays {
  try {
    const kept = window.sessionStorage.getItem(WINDOW_UNDER);
    return kept === "30" ? 30 : kept === "1" ? 1 : 7;
  } catch {
    return 7;
  }
}

function keepWindow(days: WindowDays): void {
  try {
    window.sessionStorage.setItem(WINDOW_UNDER, String(days));
  } catch {
    // Lasts only for the page.
  }
}

export function Dashboard(): ReactNode {
  const { agents, live, lines } = useOrg();
  const [days, setDays] = useState<WindowDays>(keptWindow);
  const pick = (one: WindowDays): void => {
    keepWindow(one);
    setDays(one);
  };
  const earlier = useMemo(() => utcDay(Date.now() / 1000 - days * 86400), [days]);
  const answered = useInsights(days);
  const month = useInsights(HARNESS_DAYS);
  const before = useInsights(days, { day: earlier });
  const slugs = useMemo(() => agents.map((one) => one.slug), [agents]);
  const harness = useHarness(slugs);
  const code = useMemo(() => new Set(agents.filter((one) => one.kind === "class").map((one) => one.slug)), [agents]);
  // Nothing is drawn of another window than the one picked.
  const counted = answered?.days === days ? answered : null;
  const was = before?.days === days ? before : null;

  const moved = counted === null ? null : change(counted.conversations.now, counted.conversations.before);
  const movedSaid = moved === null || was === null ? "—" : `${moved >= 0 ? "+" : "−"}${percent(Math.abs(moved))}`;

  const picker = (
    <div className="dash-switch" role="group" aria-label="Window">
      {WINDOWS.map((one) => (
        <button key={one} type="button" aria-pressed={one === days} className={one === days ? "dash-switch-on" : ""} onClick={() => pick(one)}>
          {one === 1 ? "Today" : `${one} days`}
        </button>
      ))}
    </div>
  );

  return (
    <>
      <PageHead>
        <NoticesButton />
      </PageHead>
      <div className="dash-home">
        <HarnessCards harness={harness} judged={month?.judged ?? 0} passed={month?.passed ?? 0} days={HARNESS_DAYS} />
        <Overview counted={counted} moved={movedSaid} days={days} live={live.length} picker={picker} />
        <Below counted={counted} lines={lines} code={code} />
      </div>
    </>
  );
}
