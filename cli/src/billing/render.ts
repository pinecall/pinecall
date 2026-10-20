/** The limits as a terminal reads them: the env, a line per quota, and whose keys a call runs on. */

import { fields } from "../kit/table.js";
import { QUOTAS, type Limit, type LimitsReport } from "./service.js";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** The whole answer: the env, a line per quota, the keys line, and where to buy more when the deployment sells plans. */
export function limits(report: LimitsReport): string[] {
  const next = startsAgain(report.starts_again);
  const pairs: [string, string][] = QUOTAS.map((quota) => {
    const one = report.limits[quota.name];
    return [quota.label, quota.monthly && one.limit !== null ? `${meter(one)} · starts again ${next}` : meter(one)];
  });
  pairs.push(["keys", keysLine(report.brought, report.limits.lends)]);
  const lines = [report.env, ...fields(pairs).map((line) => `  ${line}`)];
  if (report.limits.billing_url !== null) lines.push(`  more: ${report.limits.billing_url}`);
  return lines;
}

/** One quota as `used of limit`, or `used, no limit`. */
export function meter(one: Limit): string {
  const used = Number.isInteger(one.used) ? String(one.used) : one.used.toFixed(1);
  return one.limit === null ? `${used}, no limit` : `${used} of ${one.limit}`;
}

/** Whose keys a call runs on: the org's own, then what the runtime lends (null lends every key it holds). */
export function keysLine(brought: readonly string[], lends: readonly string[] | null): string {
  const yours = brought.length === 0 ? "yours: none" : `yours: ${[...brought].sort().join(", ")}`;
  if (lends === null) return `${yours} · lent by the runtime: every vendor it holds a key for`;
  if (lends.length === 0) return `${yours} · lent by the runtime: none, bring a key for every vendor`;
  return `${yours} · lent by the runtime: ${lends.join(", ")}`;
}

/** `1 Nov` from `2026-11-01`. */
function startsAgain(day: string): string {
  const month = Number(day.slice(5, 7)) - 1;
  return `${Number(day.slice(8, 10))} ${MONTHS[month] ?? ""}`.trimEnd();
}
