/** What a world refuses now, said for the strip over every screen: the quotas used up this month, or a production closed to the org. */

import type { Limits } from "@pinecall/core/wire/rest-org";
import { startsAgain } from "./format";
import { productionClosed } from "./plan";

/** The quotas a month starts again and a call, a judge or a simulation is refused past. */
export type Monthly = "minutes" | "messages" | "llm_tokens" | "budget_usd" | "evals" | "simulations";

// What each refuses when it is used up. The caps on what the org keeps — agents, numbers, seats,
// facts, chunks, apps — refuse one more of that at its own screen, and are no strip.
const REFUSES: Record<Monthly, "calls" | "judges" | "simulations"> = {
  minutes: "calls",
  messages: "calls",
  llm_tokens: "calls",
  budget_usd: "calls",
  evals: "judges",
  simulations: "simulations",
};

const NAMED: Record<Monthly, string> = {
  minutes: "minutes",
  messages: "messages",
  llm_tokens: "model tokens",
  budget_usd: "monthly spend",
  evals: "evals",
  simulations: "simulations",
};

/** One quota used up: what it is, and how much of how much. */
export interface UsedUp {
  quota: Monthly;
  used: number;
  limit: number;
}

/** The monthly quotas at or past their limit. A limit of zero is a world closed to the org, not a quota used up. */
export function usedUp(limits: Limits): UsedUp[] {
  return (Object.keys(REFUSES) as Monthly[]).flatMap((quota) => {
    const meter = limits[quota];
    return meter.limit !== null && meter.limit > 0 && meter.used >= meter.limit ? [{ quota, used: meter.used, limit: meter.limit }] : [];
  });
}

/** Production closed to the org: the free plan is the sandbox, and production opens with a plan. */
export function closedToTheOrg(limits: Limits): boolean {
  return limits.world === "production" && productionClosed(limits);
}

const CLOSED = "Production is closed to this organization: it opens with a plan. Build and test in the sandbox meanwhile.";

/** The strip's sentence: what is used up in which world, each as used of its limit, and what is refused until when. */
export function usedUpSaid(gone: readonly UsedUp[], world: Limits["world"], now: Date): string {
  const names = listed(gone.map((one) => NAMED[one.quota]));
  const counts = gone.map((one) => (one.quota === "budget_usd" ? `$${whole(one.used)} of $${one.limit}` : `${whole(one.used)} of ${one.limit} ${NAMED[one.quota]}`)).join(", ");
  const refused = listed([...new Set(gone.map((one) => REFUSES[one.quota]))]);
  return `${capitalised(names)} used up in ${world === "sandbox" ? "the sandbox" : "production"}: ${counts}. ${capitalised(refused)} are refused until they start again on ${startsAgain(now)}.`;
}

/** What the strip says, or nothing: the world closed, else what is used up. */
export function stripSaid(limits: Limits, now: Date): string | null {
  if (closedToTheOrg(limits)) return CLOSED;
  const gone = usedUp(limits);
  return gone.length === 0 ? null : usedUpSaid(gone, limits.world, now);
}

function listed(words: readonly string[]): string {
  return words.length <= 1 ? (words[0] ?? "") : `${words.slice(0, -1).join(", ")} and ${words[words.length - 1]}`;
}

function whole(value: number): string {
  return String(Math.floor(value));
}

function capitalised(word: string): string {
  return word.charAt(0).toUpperCase() + word.slice(1);
}
