/** Group metered rows by call, day and agent. */

import { utcDay } from "../../lib/format";
import type { UsageRow } from "./door";

/** Sum of a group of metered rows. */
export interface Sum {
  calls: number;
  minutes: number;
  messages: number;
  judge_calls: number;
  /** Judges that answered on Pinecall's key: what the evals meter bills. */
  evals: number;
  /** Calls a simulated caller played: what the simulations meter bills. */
  simulations: number;
  cost_usd: number;
}

/** One call's cost: its summary row plus its judges. */
export interface CallBill extends Sum {
  call: string;
  agent: string;
  at: number;
}

/** A named group (day or agent) and its sum. */
export interface Group extends Sum {
  name: string;
}

// A call writes two rows (summary and score); merge them into one.
/** One line per call, newest first. */
export function byCall(rows: readonly UsageRow[]): CallBill[] {
  const bills = new Map<string, CallBill>();
  for (const row of rows) {
    const bill = bills.get(row.call) ?? { call: row.call, agent: row.agent, at: row.at, calls: 1, minutes: 0, messages: 0, judge_calls: 0, evals: 0, simulations: 0, cost_usd: 0 };
    bill.minutes += row.minutes;
    bill.messages += row.messages;
    bill.judge_calls += row.judge_calls;
    bill.evals += row.evals;
    if (row.simulated) bill.simulations = 1;
    bill.cost_usd += row.cost_usd;
    bill.at = Math.min(bill.at, row.at);
    bills.set(row.call, bill);
  }
  return [...bills.values()].sort((one, other) => other.at - one.at);
}

function grouped(bills: readonly CallBill[], nameOf: (bill: CallBill) => string): Group[] {
  const groups = new Map<string, Group>();
  for (const bill of bills) {
    const name = nameOf(bill);
    const group = groups.get(name) ?? { name, calls: 0, minutes: 0, messages: 0, judge_calls: 0, evals: 0, simulations: 0, cost_usd: 0 };
    group.calls += 1;
    group.minutes += bill.minutes;
    group.messages += bill.messages;
    group.judge_calls += bill.judge_calls;
    group.evals += bill.evals;
    group.simulations += bill.simulations;
    group.cost_usd += bill.cost_usd;
    groups.set(name, group);
  }
  return [...groups.values()];
}

/** One line per UTC day, newest first. */
export function byDay(bills: readonly CallBill[]): Group[] {
  return grouped(bills, (bill) => utcDay(bill.at)).sort((one, other) => other.name.localeCompare(one.name));
}

/** One line per agent, the costliest first. */
export function byAgent(bills: readonly CallBill[]): Group[] {
  return grouped(bills, (bill) => bill.agent).sort((one, other) => other.cost_usd - one.cost_usd);
}

/** Everything, summed. */
export function total(bills: readonly CallBill[]): Sum {
  return grouped(bills, () => "")[0] ?? { calls: 0, minutes: 0, messages: 0, judge_calls: 0, evals: 0, simulations: 0, cost_usd: 0 };
}
