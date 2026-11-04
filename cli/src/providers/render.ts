/** Providers as a terminal reads them: the vendor table with the platform's defaults, the org's own vendors by name. */

import { table } from "../kit/table.js";
import type { Catalog, ProviderKeys } from "./service.js";

export const NO_PROVIDER_KEYS = "no provider key brought: every call runs on the keys of Pinecall";

/**
 * The vendors a call can run on, one row each; the rest on one line per standing (`no key`, `no plugin`),
 * each vendor with what it does; then how many, which the platform runs each job on, and the realtime models.
 */
export function catalog(found: Catalog): string[] {
  const running = found.providers.filter((one) => one.standing === "ready" || one.standing === "its own");
  const waiting = new Map<string, string[]>();
  for (const one of found.providers) {
    if (running.includes(one)) continue;
    waiting.set(one.standing, [...(waiting.get(one.standing) ?? []), `${one.name} (${one.does.join(",")})`]);
  }
  const rows = table(
    ["vendor", "does", "standing"],
    running.map((one) => [one.name, one.does.join(","), one.standing]),
  );
  const rest = [...waiting].map(([standing, vendors]) => `${standing}: ${vendors.join(", ")}${standing === "no key" ? " · `pinecall providers add <vendor>` brings one" : ""}`);
  const ours = Object.entries(found.defaults).map(([job, vendor]) => `${job} ${vendor}`);
  const spoken = Object.entries(found.realtime ?? {}).map(([vendor, models]) => `realtime · ${vendor}: ${models.join(", ")}`);
  return [...rows, ...(rows.length > 0 && rest.length > 0 ? [""] : []), ...rest, "", `${found.providers.length} vendors · ours: ${ours.join(" · ")}`, ...spoken];
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
