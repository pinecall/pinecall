/** Providers screen API: the vendor catalog and the org's own vendor keys. */

import { z } from "zod";

import { drop, put, read, type Credentials } from "@pinecall/core/api";

export { readCatalogue } from "../../lib/catalogue";
export type { Catalogue, Provider } from "../../lib/catalogue";

// Returns vendor names only, never a key, prefix or fingerprint: only the worker reads keys back.
const BroughtSchema = z.object({ vendors: z.array(z.string()) });

/** Vendors this org runs on its own key; the rest use the box's key. */
export async function readVendors(credentials: Credentials): Promise<string[]> {
  return BroughtSchema.parse(await read(credentials, "/v1/provider-keys")).vendors;
}

/** Upload a vendor key. The page keeps no copy. */
export async function addKey(credentials: Credentials, vendor: string, key: string): Promise<void> {
  await put(credentials, `/v1/provider-keys/${encodeURIComponent(vendor)}`, { key });
}

/** Revert a vendor to the box's key, effective from the next call. */
export async function removeKey(credentials: Credentials, vendor: string): Promise<void> {
  await drop(credentials, `/v1/provider-keys/${encodeURIComponent(vendor)}`);
}
