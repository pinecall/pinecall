/** GET /v1/whoami: schema, request and the org's display name. */

import { z } from "zod";

import { read, type Credentials } from "./api";

// Never includes the key or its hash.
const WhoseSchema = z.object({
  org: z.string(),
  /** Human-readable org name (`clinica`); `org` is the id and may differ. */
  slug: z.string().nullish(),
  key_id: z.string(),
  label: z.string().nullish(),
  env: z.enum(["production", "sandbox"]),
  scopes: z.array(z.string()),
  subject: z.string().nullish(),
  name: z.string().nullish(),
  /** The person is the box operator. */
  operator: z.boolean().optional(),
  /** Operator viewing an org they are not a member of. */
  visiting: z.boolean().optional(),
  /** May act in production (the person's switch, always for admins, or a production token). */
  production: z.boolean(),
});
export type Whose = z.infer<typeof WhoseSchema>;

/** Resolve who the credentials belong to. */
export async function whoami(credentials: Credentials): Promise<Whose> {
  return WhoseSchema.parse(await read(credentials, "/v1/whoami"));
}

/** The org's slug for display, falling back to its id when there is none. */
export function orgOf(whose: Whose): string {
  return whose.slug ?? whose.org;
}
