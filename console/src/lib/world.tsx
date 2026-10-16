/** Context for the current world, sandbox corner and org switching. */

import { createContext, useContext, type ReactNode } from "react";

import type { World } from "./mode";

export interface Worlds {
  world: World;
  /** Switch to another of the person's orgs (mints a key there) and reopen at `landing` or root. */
  moveTo: (org: string, landing?: string) => Promise<void>;
  /** The colleague's member id whose sandbox copy is shown, or null for one's own. */
  corner: string | null;
  /** Admin-only in the sandbox: view a colleague's copy, or null for one's own. */
  lookInto: (corner: string | null) => void;
}

const Held = createContext<Worlds | null>(null);

export function WorldProvider({ value, children }: { value: Worlds; children: ReactNode }): ReactNode {
  return <Held value={value}>{children}</Held>;
}

/** The world context; throws if no provider is mounted. */
export function useWorld(): Worlds {
  const held = useContext(Held);
  if (held === null) throw new Error("the console was mounted without a world");
  return held;
}
