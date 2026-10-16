/** The machine label shown on keys minted for this terminal. */

import { hostname as osHostname } from "node:os";

/** The hostname, or "cli" when it cannot be read. */
export function hostname(): string {
  try {
    return osHostname();
  } catch {
    return "cli";
  }
}
