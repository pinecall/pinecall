/** The billing endpoint: what the org may use in an env and what it used. */

import type { GatewayClient } from "./client.js";

/** One quota of `GET /v1/limits`: a null limit is no limit, 0 a limit that refuses everything. */
export interface Limit {
  limit: number | null;
  used: number;
}

/** `GET /v1/limits`, as the gateway answers it. */
export interface Limits {
  minutes: Limit;
  messages: Limit;
  llm_tokens: Limit;
  concurrent_calls: Limit;
  agents: Limit;
  seats: Limit;
  numbers: Limit;
  evals: Limit;
  simulations: Limit;
  /** The vendors the runtime lends the org a key for; null lends every key it holds. */
  lends: string[] | null;
  /** Where the org buys more, when the deployment sells plans. */
  billing_url: string | null;
  /** The env the limits are of, under the gateway's own field name. */
  world: string;
}

export function getLimits(gw: GatewayClient): Promise<Limits> {
  return gw.get<Limits>("/v1/limits");
}
