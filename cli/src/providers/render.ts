/** Providers as a terminal reads them: the vendor table with the platform's defaults, the org's own vendors by name. */

import { formatHint } from "../kit/format.js";
import { table } from "../kit/table.js";
import type { Catalog, ProviderKeys } from "./service.js";

export const NO_PROVIDER_KEYS = "no provider key brought: every call runs on the keys of Pinecall";

/**
 * The vendors a call can run on, one row each, then how many wait on something (a key, a plugin)
 * and which vendor the platform runs each job on. `all` lists every vendor with its standing, and
 * the realtime models one row a vendor.
 */
export function catalog(found: Catalog, all = false): string[] {
  const running = found.providers.filter((one) => one.standing === "ready" || one.standing === "its own");
  const listed = all ? found.providers : running;
  const rows = table(["vendor", "does", "standing"], listed.map((one) => [one.name, one.does.join(" "), one.standing]));
  const waiting = new Map<string, number>();
  for (const one of found.providers) if (!running.includes(one)) waiting.set(one.standing, (waiting.get(one.standing) ?? 0) + 1);
  const rest = [...waiting].map(([standing, n]) => `${n} ${standing === "no key" ? "have no key" : `stand at ${standing}`}`);
  const ours = Object.entries(found.defaults).map(([job, vendor]) => `${job} ${vendor}`);
  const summary = [`${running.length} run a call here`, ...rest, ...(ours.length === 0 ? [] : [`ours: ${ours.join(" · ")}`])].join(" · ");
  const realtime = Object.entries(found.realtime ?? {});
  const spoken = all && realtime.length > 0 ? ["", ...table(["realtime", "models"], realtime.map(([vendor, models]) => [vendor, models.join(", ")]))] : [];
  const steps = [...(waiting.has("no key") ? ["pinecall providers add <vendor> brings a key"] : []), ...(all ? [] : ["--all lists every vendor and the realtime models"])];
  return [...rows, summary, ...spoken, ...(steps.length === 0 ? [] : [formatHint(...steps)])];
}

/** The org's own vendors, one per line, and nothing else: not a value, not a prefix, not a fingerprint. */
export function providerKeys(found: ProviderKeys): string[] {
  return found.vendors.length === 0 ? [NO_PROVIDER_KEYS] : found.vendors;
}

export function providerKeyAdded({ vendor }: { vendor: string }): string {
  return vendor;
}

export function providerKeyRemoved({ vendor }: { vendor: string }): string {
  return vendor;
}
