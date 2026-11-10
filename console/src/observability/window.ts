/** The window and the agent Observability is read over: in the address when picked, the week otherwise, and the month when the week holds nothing. */

import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router";

import type { WindowDays } from "../lib/insights";

export const WINDOWS: readonly { days: WindowDays; label: string; said: string }[] = [
  { days: 1, label: "Today", said: "today" },
  { days: 7, label: "7 days", said: "the last 7 days" },
  { days: 30, label: "30 days", said: "the last 30 days" },
];

const OPENS_ON: WindowDays = 7;
const WIDENS_TO: WindowDays = 30;

/** How a window is said in a sentence: "today", "the last 7 days". */
export function windowSaid(days: WindowDays): string {
  return WINDOWS.find((one) => one.days === days)?.said ?? "today";
}

export interface OpeningWindow {
  days: WindowDays;
  /** The agent in view, "" for every agent. */
  agent: string;
  pick: (days: WindowDays) => void;
  pickAgent: (agent: string) => void;
  /** A window was picked, in the address or by hand: the page never moves off it by itself. */
  picked: boolean;
  /** Move to the month, for this agent, the week having held nothing. */
  widen: () => void;
}

export function useOpeningWindow(): OpeningWindow {
  const [search, setSearch] = useSearchParams();
  const agent = search.get("agent") ?? "";
  const asked = Number(search.get("days"));
  const inAddress = WINDOWS.find((one) => one.days === asked)?.days;
  // The week picked by hand leaves no trace in the address, being what it opens on.
  const [byHand, setByHand] = useState(false);
  const [widenedFor, setWidenedFor] = useState<string | null>(null);

  const write = useCallback(
    (name: string, value: string): void => {
      setSearch(
        (was) => {
          const next = new URLSearchParams(was);
          if (value === "") next.delete(name);
          else next.set(name, value);
          return next;
        },
        { replace: true },
      );
    },
    [setSearch],
  );

  const picked = inAddress !== undefined || byHand;
  const widen = useCallback(() => setWidenedFor(agent), [agent]);
  const pick = (chosen: WindowDays): void => {
    setByHand(true);
    write("days", chosen === OPENS_ON ? "" : String(chosen));
  };
  const pickAgent = (chosen: string): void => write("agent", chosen);
  return { days: picked ? (inAddress ?? OPENS_ON) : widenedFor === agent ? WIDENS_TO : OPENS_ON, agent, pick, pickAgent, picked, widen };
}

/**
 * Widen an unpicked week that holds nothing to the month, and say whether the window is still
 * being decided: `quiet` is whether the window read holds nothing, null until it is read. Until
 * then the page draws its head alone, not cards it may take back.
 */
export function useWidenedWhenQuiet({ days, picked, widen }: OpeningWindow, quiet: boolean | null): boolean {
  const opening = !picked && days === OPENS_ON;
  useEffect(() => {
    if (opening && quiet === true) widen();
  }, [opening, quiet, widen]);
  return quiet === null || (opening && quiet);
}
