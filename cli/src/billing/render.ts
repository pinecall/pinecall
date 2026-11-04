/** The limits as a terminal reads them: the env, a line per quota, and whose keys a call runs on. */

import { amount, formatHint } from "../kit/format.js";
import { table } from "../kit/table.js";
import { QUOTAS, type Limit, type LimitsReport } from "./service.js";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/**
 * The whole answer: the env, a line per quota something was used of or a limit is set on, the quotas
 * untouched and unlimited on one line, the keys line, and where to buy more when the deployment sells plans.
 */
export function limits(report: LimitsReport): string[] {
  const next = startsAgain(report.starts_again);
  const untouched = QUOTAS.filter((quota) => report.limits[quota.name].used === 0 && report.limits[quota.name].limit === null);
  const used = QUOTAS.filter((quota) => !untouched.includes(quota));
  const monthly = used.some((quota) => quota.monthly && report.limits[quota.name].limit !== null);
  const rows = table(
    ["quota", "used", "limit", ...(monthly ? ["starts again"] : [])],
    used.map((quota) => {
      const one = report.limits[quota.name];
      const spent = quota.dollars === true ? `$${one.used.toFixed(2)}` : amount(one.used);
      const most = one.limit === null ? "—" : quota.dollars === true ? `$${one.limit}` : amount(one.limit);
      return [quota.label, spent, most, ...(monthly ? [quota.monthly && one.limit !== null ? next : ""] : [])];
    }),
  );
  const lines = [report.env, ...rows];
  if (untouched.length > 0) lines.push(untouched.length === QUOTAS.length ? "nothing used, no limit on any quota" : `nothing used, no limit: ${untouched.map((quota) => quota.label).join(" · ")}`);
  lines.push(`keys  ${keysLine(report.brought, report.limits.lends)}`);
  if (report.limits.billing_url !== null) lines.push(formatHint(`${report.limits.billing_url} buys more`));
  return lines;
}

/** One quota as `used of limit`, or `used · no limit`. */
export function meter(one: Limit): string {
  const used = Number.isInteger(one.used) ? String(one.used) : one.used.toFixed(1);
  return one.limit === null ? `${used} · no limit` : `${used} of ${one.limit}`;
}

/** One quota in dollars, to the cent: `$4.25 of $60`, or `$4.25 · no limit`. */
export function dollars(one: Limit): string {
  const used = `$${one.used.toFixed(2)}`;
  return one.limit === null ? `${used} · no limit` : `${used} of $${one.limit}`;
}

/** Whose keys a call runs on: the org's own, then what the runtime lends (null lends every key it holds). */
export function keysLine(brought: readonly string[], lends: readonly string[] | null): string {
  const yours = brought.length === 0 ? "yours: none" : `yours: ${[...brought].sort().join(", ")}`;
  if (lends === null) return `${yours} · the runtime lends the rest`;
  if (lends.length === 0) return `${yours} · the runtime lends none: bring a key for every vendor`;
  return `${yours} · the runtime lends ${lends.join(", ")}`;
}

/** `1 Nov` from `2026-11-01`. */
function startsAgain(day: string): string {
  const month = Number(day.slice(5, 7)) - 1;
  return `${Number(day.slice(8, 10))} ${MONTHS[month] ?? ""}`.trimEnd();
}
