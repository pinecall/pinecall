/** Tracks the previous path so detail screens can link back to where the reader came from. */

import { createContext, useContext, useRef, type ReactNode } from "react";
import { useLocation } from "react-router";

import { screenAt } from "./mode";

// Detail screens are reached from several lists, so a hardcoded back link is wrong from most of
// them. With no previous path (reload, pasted URL) the screen's own fallback is used.
const Whence = createContext<string | null>(null);

/** Provider that remembers the previous path. Mount once around the screens. */
export function WhenceKeeper({ children }: { children: ReactNode }): ReactNode {
  const { pathname, search } = useLocation();
  const here = `${pathname}${search}`;
  // Updated during render, not in an effect, so children see the new value in the same pass.
  const seen = useRef<{ now: string; before: string | null }>({ now: here, before: null });
  if (seen.current.now !== here) {
    seen.current = { now: here, before: seen.current.now };
  }
  return <Whence.Provider value={seen.current.before}>{children}</Whence.Provider>;
}

/** The previous path, or null on first load. */
export function useWhence(): string | null {
  return useContext(Whence);
}

export interface WayBack {
  to: string;
  name: string;
}

/** Back link target: the previous in-app path, else `fallback`; named from the screens table. */
export function useWayBack(fallback: string): WayBack {
  const whence = useWhence();
  const { pathname, search } = useLocation();
  const inside = whence !== null && whence.startsWith("/") && !whence.startsWith("//");
  const to = inside && whence !== `${pathname}${search}` ? whence : fallback;
  return { to, name: screenAt(to)?.name ?? "Back" };
}
