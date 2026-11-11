// What a part of the screen may do: tell the agent what the caller did on the page, while the call is live.

import { createContext, useContext } from "react";

export interface Page {
  /** False once the call ended: the screen stays, and nothing on it answers a tap. */
  live: boolean;
  tell(name: string, data: Record<string, unknown>): void;
}

export const PageContext = createContext<Page>({ live: false, tell: () => {} });

export function usePage(): Page {
  return useContext(PageContext);
}
