/** Whether the welcome guide is due: an org that holds no agent and has not been through it or skipped it. */

import { welcomed } from "../../lib/preferences";

/** Due once the org's agents are known and there are none. */
export function isFirstRun(agentsLoaded: boolean, agents: number): boolean {
  return agentsLoaded && agents === 0 && !welcomed();
}
