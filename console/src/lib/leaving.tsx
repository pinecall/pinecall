/** Context for the sign-out callback provided by main.tsx. */

import { createContext, useContext, type ReactNode } from "react";

const Held = createContext<(() => void) | null>(null);

export function LeavingProvider({ value, children }: { value: () => void; children: ReactNode }): ReactNode {
  return <Held value={value}>{children}</Held>;
}

/** The sign-out callback; throws if no provider is mounted. */
export function useLeaving(): () => void {
  const held = useContext(Held);
  if (held === null) throw new Error("the console was mounted without a way out");
  return held;
}
