/** Org members: schema and GET /v1/members (`team` scope). */

import { z } from "zod";

import { read, type Credentials } from "./api";

// Not in the wire yet; shared by the console and mobile apps.

/** Member roles (runtime types/member.py). */
export const ROLES = ["qa", "supervisor", "manager", "admin", "developer"] as const;
/** Member status. */
export const STATUSES = ["invited", "active", "disabled"] as const;

export const MemberSchema = z.object({
  id: z.string(),
  email: z.string(),
  name: z.string(),
  role: z.enum(ROLES),
  agents: z.array(z.string()),
  status: z.enum(STATUSES),
  scopes: z.array(z.string()),
  /** May act in production (granted by an admin, or is one). */
  production: z.boolean(),
});
export type Member = z.infer<typeof MemberSchema>;

/** All org members, oldest first, including disabled ones. */
export async function readMembers(credentials: Credentials): Promise<Member[]> {
  return z.object({ members: z.array(MemberSchema) }).parse(await read(credentials, "/v1/members")).members;
}
