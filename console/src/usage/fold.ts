/** Usage, folded: a quota as a meter, and the metered rows by call, by day and by agent. */

import { count, money, utcDay } from "../lib/format";
import type { Limits, UsageRow } from "./door";

export type MeterKey = "minutes" | "messages" | "llm_tokens" | "evals" | "simulations" | "budget_usd" | "agents" | "seats" | "numbers" | "hosted_apps" | "memory_facts" | "knowledge_chunks" | "concurrent_calls";

/** What is metered a month, then what the org holds now. */
export const MONTHLY: readonly MeterKey[] = ["minutes", "messages", "llm_tokens", "evals", "simulations", "budget_usd"];
export const HELD: readonly MeterKey[] = ["agents", "seats", "numbers", "hosted_apps", "memory_facts", "knowledge_chunks", "concurrent_calls"];

const NAMES: Readonly<Record<string, { name: string; about: string }>> = {
  minutes: { name: "Minutes", about: "Of calls" },
  messages: { name: "Messages", about: "Chat and WhatsApp turns" },
  llm_tokens: { name: "LLM tokens", about: "In and out" },
  evals: { name: "Evals", about: "Judges on the platform's key" },
  simulations: { name: "Simulations", about: "Calls a simulated caller played" },
  budget_usd: { name: "Spend", about: "Both environments" },
  agents: { name: "Agents", about: "Held" },
  seats: { name: "Seats", about: "People in the org" },
  numbers: { name: "Numbers", about: "Phone numbers" },
  hosted_apps: { name: "Hosted apps", about: "Run by the platform" },
  memory_facts: { name: "Memory facts", about: "Kept about callers" },
  knowledge_chunks: { name: "Knowledge chunks", about: "Indexed" },
  concurrent_calls: { name: "Calls at once", about: "Live right now" },
};

export type Mood = "calm" | "warn" | "bad";

export interface Meter {
  key: MeterKey;
  name: string;
  about: string;
  used: string;
  /** Null: no limit. */
  limit: string | null;
  /** Used of the limit, 0 to 1; null with no limit. */
  share: number | null;
  mood: Mood;
}

/** `$1.23`, and four decimals under a cent. */
export function spent(value: number): string {
  return value > 0 && value < 0.01 ? `$${value.toFixed(4)}` : money(value);
}

/** A count as a person reads it: whole, or one decimal when it is small and not whole. */
export function amount(value: number): string {
  return Number.isInteger(value) || value >= 1000 ? count(Math.round(value)) : value.toFixed(1);
}

export function meterOf(key: MeterKey, limits: Limits): Meter {
  const { limit, used } = limits[key];
  const said = key === "budget_usd" ? spent : amount;
  const share = limit === null ? null : limit <= 0 ? 1 : Math.min(1, Math.max(0, used / limit));
  const mood: Mood = share === null ? "calm" : share >= 1 ? "bad" : share > 0.8 ? "warn" : "calm";
  return { key, name: NAMES[key]?.name ?? key, about: NAMES[key]?.about ?? "", used: said(used), limit: limit === null ? null : said(limit), share, mood };
}

export interface Sum {
  calls: number;
  minutes: number;
  messages: number;
  tokens: number;
  evals: number;
  simulations: number;
  cost_usd: number;
  caller_cost_usd: number;
  /** Minutes of calls a stage of which ran on the platform's key. */
  lent_minutes: number;
}

const NOTHING: Sum = { calls: 0, minutes: 0, messages: 0, tokens: 0, evals: 0, simulations: 0, cost_usd: 0, caller_cost_usd: 0, lent_minutes: 0 };

/** One call's rows as one line. */
export interface CallBill extends Sum {
  call: string;
  agent: string;
  at: number;
}

export interface Group extends Sum {
  name: string;
}

/** A call writes several rows (its summary, its score): one line a call, and one for each row of no call. */
export function byCall(rows: readonly UsageRow[]): CallBill[] {
  const bills = new Map<string, CallBill>();
  for (const row of rows) {
    const under = row.call === "" ? `row ${row.cursor}` : row.call;
    const bill = bills.get(under) ?? { ...NOTHING, call: row.call, agent: row.agent, at: row.at, calls: row.call === "" ? 0 : 1 };
    bill.minutes += row.minutes;
    bill.messages += row.messages;
    bill.tokens += row.input_tokens + row.output_tokens;
    bill.evals += row.evals;
    if (row.simulated) bill.simulations = 1;
    bill.cost_usd += row.cost_usd;
    bill.caller_cost_usd += row.caller_cost_usd;
    if (row.lent.length > 0) bill.lent_minutes += row.minutes;
    bill.at = Math.min(bill.at, row.at);
    bills.set(under, bill);
  }
  return [...bills.values()];
}

function add(to: Sum, bill: Sum): void {
  to.calls += bill.calls;
  to.minutes += bill.minutes;
  to.messages += bill.messages;
  to.tokens += bill.tokens;
  to.evals += bill.evals;
  to.simulations += bill.simulations;
  to.cost_usd += bill.cost_usd;
  to.caller_cost_usd += bill.caller_cost_usd;
  to.lent_minutes += bill.lent_minutes;
}

function grouped(bills: readonly CallBill[], nameOf: (bill: CallBill) => string): Map<string, Group> {
  const groups = new Map<string, Group>();
  for (const bill of bills) {
    const name = nameOf(bill);
    const group = groups.get(name) ?? { ...NOTHING, name };
    add(group, bill);
    groups.set(name, group);
  }
  return groups;
}

export function total(bills: readonly CallBill[]): Sum {
  const all = { ...NOTHING };
  for (const bill of bills) add(all, bill);
  return all;
}

/** The last `days` UTC days ending on the day of `now`, oldest first, a day of nothing included. */
export function lastDays(bills: readonly CallBill[], days: number, now: number): Group[] {
  const found = grouped(bills, (bill) => utcDay(bill.at));
  return Array.from({ length: days }, (_, at) => {
    const day = utcDay(now - (days - 1 - at) * 86400);
    return found.get(day) ?? { ...NOTHING, name: day };
  });
}

export type Measure = "cost" | "minutes" | "calls";

export function measured(sum: Sum, measure: Measure): number {
  return measure === "cost" ? sum.cost_usd : measure === "minutes" ? sum.minutes : sum.calls;
}

export function saidOf(measure: Measure, value: number): string {
  return measure === "cost" ? spent(value) : measure === "minutes" ? `${value.toFixed(1)} min` : count(Math.round(value));
}

/** One line an agent, the most of the measure first. */
export function byAgent(bills: readonly CallBill[], measure: Measure): Group[] {
  return [...grouped(bills, (bill) => bill.agent).values()].sort((one, other) => measured(other, measure) - measured(one, measure) || one.name.localeCompare(other.name));
}

/** The calls that cost the most, the costliest first. */
export function costliest(bills: readonly CallBill[], most: number): CallBill[] {
  return bills
    .filter((bill) => bill.call !== "" && bill.cost_usd > 0)
    .sort((one, other) => other.cost_usd - one.cost_usd)
    .slice(0, most);
}
