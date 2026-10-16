/** `GET /v1/memory`: paged facts across every agent of the org. */

import { z } from "zod";

import { GatewayError, read, type Credentials } from "@pinecall/core/api";

const OrgFactSchema = z.object({
  id: z.string(),
  agent: z.string(),
  contact: z.string(),
  text: z.string(),
  category: z.string().nullish(),
  written_at: z.number(),
});
export type OrgFact = z.infer<typeof OrgFactSchema>;

const OrgMemorySchema = z.object({ facts: z.array(OrgFactSchema), next: z.string().nullish() });
export type OrgMemoryPage = z.infer<typeof OrgMemorySchema>;

// 404 means memory is not configured, which must not render as an empty table.
/** One page matching `words` after the cursor, or null when memory is off. */
export async function readOrgMemory(credentials: Credentials, words: string, after: string | null): Promise<OrgMemoryPage | null> {
  const params: Record<string, string> = {};
  if (words !== "") params["q"] = words;
  if (after !== null) params["after"] = after;
  try {
    return OrgMemorySchema.parse(await read(credentials, "/v1/memory", params));
  } catch (failed) {
    if (failed instanceof GatewayError && failed.status === 404) return null;
    throw failed;
  }
}
