/** The `this.knowledge` interface: search the knowledge bases attached to the agent. */

import type { Found } from "../call/call.js";

/** Search the attached knowledge bases and return the top `k` chunks for `query`. */

export interface Knowledge {
  search(query: string, options?: { k?: number }): Promise<Found[]>;
}
