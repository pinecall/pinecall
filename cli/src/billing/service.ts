/** Billing: what the org may use in this env, what it used this month, and whose keys its calls run on. */

import * as api from "../api/billing.js";
import { listProviderKeys } from "../api/providers.js";
import type { Context } from "../context.js";

export type { Limit, Limits } from "../api/billing.js";

/** One quota as the report names it: monthly ones start again on the first of the month (UTC), the rest are what the org holds now. */
export interface Quota {
  name: keyof Pick<api.Limits, "minutes" | "messages" | "llm_tokens" | "evals" | "simulations" | "concurrent_calls" | "agents" | "seats" | "numbers">;
  label: string;
  monthly: boolean;
}

/** The quotas in print order. */
export const QUOTAS: readonly Quota[] = [
  { name: "minutes", label: "minutes", monthly: true },
  { name: "messages", label: "messages", monthly: true },
  { name: "llm_tokens", label: "LLM tokens", monthly: true },
  { name: "evals", label: "evals", monthly: true },
  { name: "simulations", label: "simulations", monthly: true },
  { name: "concurrent_calls", label: "calls at once", monthly: false },
  { name: "agents", label: "agents", monthly: false },
  { name: "seats", label: "seats", monthly: false },
  { name: "numbers", label: "bought numbers", monthly: false },
];

/** What `limits` answers: the env's limits, the vendors the org brought keys for, and the day the monthly quotas start again. */
export interface LimitsReport {
  env: string;
  limits: api.Limits;
  /** The vendors the org brought a key for, sorted. */
  brought: string[];
  /** The first of next month (UTC) as `YYYY-MM-DD`: when the monthly quotas start again. */
  starts_again: string;
}

/** The limits of this env with what is used of them, and whose keys a call runs on. */
export async function getLimits(ctx: Context, now: Date = new Date()): Promise<LimitsReport> {
  const gw = ctx.gateway();
  const limits = await api.getLimits(gw);
  const brought = await listProviderKeys(gw);
  return { env: limits.world, limits, brought: [...brought].sort(), starts_again: firstOfNextMonth(now) };
}

function firstOfNextMonth(now: Date): string {
  return new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() + 1, 1)).toISOString().slice(0, 10);
}
