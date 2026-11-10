/** The window Quality reads over, kept in its address: the week unless one was picked, and the month when the week judged nothing. */

import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router";

import type { WindowDays } from "../lib/insights";

/** The windows the page offers, with how each is said in a sentence and what it is compared with. */
export const WINDOWS: readonly { days: WindowDays; name: string; said: string; before: string }[] = [
  { days: 1, name: "Today", said: "today", before: "the day before" },
  { days: 7, name: "7 days", said: "the last 7 days", before: "the week before" },
  { days: 30, name: "30 days", said: "the last 30 days", before: "the 30 days before" },
];

const OPENS_ON: WindowDays = 7;
const WIDENS_TO: WindowDays = 30;

function wordsOf(days: WindowDays): (typeof WINDOWS)[number] | undefined {
  return WINDOWS.find((one) => one.days === days);
}

/** "the last 7 days". */
export function windowSaid(days: WindowDays): string {
  return wordsOf(days)?.said ?? "today";
}

/** "the week before". */
export function beforeSaid(days: WindowDays): string {
  return wordsOf(days)?.before ?? "the window before";
}

export interface OpeningWindow {
  days: WindowDays;
  pick: (days: WindowDays) => void;
  /** A window was picked, in the address or by hand: the page never moves off it on its own. */
  picked: boolean;
  /** Move to the month, the week having judged nothing. */
  widen: () => void;
}

/** The window picked (`?days=`, which forgets the week, being where the page opens), else the week, and the month once the week was found quiet. */
export function useOpeningWindow(): OpeningWindow {
  const [params, setParams] = useSearchParams();
  const [byHand, setByHand] = useState(false);
  const [widened, setWidened] = useState(false);
  const asked = Number(params.get("days"));
  const inAddress = WINDOWS.find((one) => one.days === asked)?.days;
  const picked = inAddress !== undefined || byHand;
  const widen = useCallback(() => setWidened(true), []);
  const pick = useCallback(
    (chosen: WindowDays): void => {
      setByHand(true);
      setParams(
        (was) => {
          const next = new URLSearchParams(was);
          if (chosen === OPENS_ON) next.delete("days");
          else next.set("days", String(chosen));
          return next;
        },
        { replace: true },
      );
    },
    [setParams],
  );
  return { days: picked ? (inAddress ?? OPENS_ON) : widened ? WIDENS_TO : OPENS_ON, pick, picked, widen };
}

/**
 * Widens an unpicked week that judged nothing to the month, and says whether the window is still
 * being decided: `quiet` is whether the window read judged nothing, null until it is read. Until
 * then the page draws no card it may have to take back.
 */
export function useWidenedWhenQuiet({ days, picked, widen }: OpeningWindow, quiet: boolean | null): boolean {
  const opening = !picked && days === OPENS_ON;
  useEffect(() => {
    if (opening && quiet === true) widen();
  }, [opening, quiet, widen]);
  return quiet === null || (opening && quiet);
}
