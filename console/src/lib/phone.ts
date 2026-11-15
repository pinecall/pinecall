/** Whether the page is drawn at a phone's width: the one breakpoint where the frame becomes an app's, read by the pages that behave differently there. */

import { useSyncExternalStore } from "react";

/** The width under which the console is laid out for a phone; every stylesheet's phone rules use the same 760px. */
export const PHONE = "(max-width: 760px)";

const asked = (): MediaQueryList => window.matchMedia(PHONE);

function follow(changed: () => void): () => void {
  const query = asked();
  query.addEventListener("change", changed);
  return () => query.removeEventListener("change", changed);
}

/** True while the window is a phone's width; it follows a rotation or a resize. */
export function usePhone(): boolean {
  return useSyncExternalStore(follow, () => asked().matches, () => false);
}
