/** Whether the list shows one row per person or one per call: each person's own choice, kept in this browser. */

import { useCallback, useState } from "react";

const KEPT_UNDER = "pinecall.calls.grouped";

function kept(): boolean {
  try {
    return window.localStorage.getItem(KEPT_UNDER) === "1";
  } catch {
    return false;
  }
}

/** One row per call unless the person grouped them. */
export function useGrouped(): [boolean, () => void] {
  const [grouped, setGrouped] = useState(kept);
  const flip = useCallback((): void => {
    setGrouped((was) => {
      try {
        window.localStorage.setItem(KEPT_UNDER, was ? "0" : "1");
      } catch {
        // Asked again on the next load.
      }
      return !was;
    });
  }, []);
  return [grouped, flip];
}
