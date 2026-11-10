/** The clock of what is still happening: the one thing on this page that moves without the log moving. */

import { useEffect, useState } from "react";

/** The time now, in seconds, ticking while asked to. */
export function useNow(ticking: boolean): number {
  const [now, setNow] = useState(() => Date.now() / 1000);
  useEffect(() => {
    if (!ticking) return;
    const timer = window.setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => window.clearInterval(timer);
  }, [ticking]);
  return now;
}
