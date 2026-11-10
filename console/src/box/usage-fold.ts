/** The deployment's usage, folded: the rows of a window, one line an organization, and the days drawn. */

import { byCall, lastDays, measured, total, type CallBill, type Group, type Measure, type Sum } from "../usage/fold";
import type { BoxUsageRow } from "./usage-door";

export type Window = "week" | "month" | "all";

/** How many days a window reaches back; null for everything the feed keeps. */
export const DAYS: Readonly<Record<Window, number | null>> = { week: 7, month: 30, all: null };

/** The rows of the window: its last days, today among them, by the UTC day. */
export function within(rows: readonly BoxUsageRow[], window: Window, now: number): BoxUsageRow[] {
  const days = DAYS[window];
  if (days === null) return [...rows];
  const from = (Math.floor(now / 86400) - (days - 1)) * 86400;
  return rows.filter((row) => row.at >= from);
}

/** One organization's use: its sums, how many agents ran, and when it was last metered. */
export interface OrgUse extends Sum {
  /** The organization's id, as the feed says it. */
  org: string;
  agents: number;
  last: number;
}

export interface Folded {
  /** One line an organization, the most of the measure first. */
  orgs: OrgUse[];
  all: Sum;
  /** A call's rows as one line, every organization's. */
  bills: CallBill[];
}

/** A call's id is its own across organizations, but its rows are folded an organization at a time so each keeps its own. */
export function fold(rows: readonly BoxUsageRow[], measure: Measure): Folded {
  const by = new Map<string, BoxUsageRow[]>();
  for (const row of rows) {
    const own = by.get(row.org);
    if (own === undefined) by.set(row.org, [row]);
    else own.push(row);
  }
  const bills: CallBill[] = [];
  const orgs: OrgUse[] = [];
  for (const [org, own] of by) {
    const mine = byCall(own);
    bills.push(...mine);
    orgs.push({ ...total(mine), org, agents: new Set(own.map((row) => row.agent)).size, last: own.reduce((latest, row) => Math.max(latest, row.at), 0) });
  }
  orgs.sort((one, other) => measured(other, measure) - measured(one, measure) || other.last - one.last);
  return { orgs, all: total(bills), bills };
}

/** The days a window draws, oldest first: its own, or the last thirty of everything. */
export function daysOf(bills: readonly CallBill[], window: Window, now: number): Group[] {
  return lastDays(bills, DAYS[window] ?? 30, now);
}
