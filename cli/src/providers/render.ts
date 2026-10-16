/** Providers as a terminal reads them: the vendor table with the platform's defaults, the org's own vendors by name. */

import { table } from "../kit/table.js";
import type { Catalog, ProviderKeys } from "./service.js";

export const NO_PROVIDER_KEYS = "no provider key brought: every call runs on the keys of Pinecall";

/** The vendors, one row each, then how many and which the platform runs each job on. */
export function catalog(found: Catalog): string[] {
  const rows = table(
    ["vendor", "does", "standing"],
    found.providers.map((one) => [one.name, one.does.join(","), one.standing]),
  );
  const ours = Object.entries(found.defaults).map(([job, vendor]) => `${job} ${vendor}`);
  return [...rows, "", `${found.providers.length} vendors · ours: ${ours.join(" · ")}`];
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
