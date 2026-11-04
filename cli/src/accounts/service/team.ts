/** The org's people: listed, a password set for one by an admin, or a one-use link that lets them choose it. */

import { z } from "zod";

import * as api from "../../api/accounts.js";
import type { Context } from "../../context.js";
import { UsageError } from "../../errors.js";

/** What `team password` takes: whose, and the password read off a terminal or stdin, never a flag. */
export const SetPasswordInput = z.object({
  email: z.string().min(1),
  password: z.string(),
});
export type SetPasswordInput = z.infer<typeof SetPasswordInput>;

/** A one-use link, and whom it is for. */
export interface ResetLink {
  email: string;
  link: string | null;
  mailed: boolean;
}

export async function listTeam(ctx: Context): Promise<api.MemberRow[]> {
  return (await api.listMembers(ctx.gateway())).members;
}

/**
 * A member id (`m_18a0c129f20e`) as the person's name, for the rows that say who wrote them. A
 * server's token may not list the org's people: then, and for an id that is no member's, the id.
 */
export async function getMemberNames(ctx: Context): Promise<(id: string) => string> {
  try {
    const named = new Map((await listTeam(ctx)).map((one) => [one.id, one.name || one.email]));
    return (id) => named.get(id) ?? id;
  } catch {
    return (id) => id;
  }
}

/** The member's password set; the gateway holds its floor and refuses a disabled member by name. */
export async function setTeamPassword(ctx: Context, input: SetPasswordInput): Promise<api.MemberRow> {
  if (input.password === "") throw new UsageError(`no password for ${input.email}: type it, or pipe it in`);
  const member = await memberNamed(ctx, input.email);
  return api.setMemberPassword(ctx.gateway(), member.id, input.password);
}

/** A link the person opens to choose their own password: no password passes through whoever asked. */
export async function resetLink(ctx: Context, email: string): Promise<ResetLink> {
  const member = await memberNamed(ctx, email);
  const invited = await api.resetMember(ctx.gateway(), member.id);
  return { email: member.email, link: invited.link ?? null, mailed: invited.mailed };
}

async function memberNamed(ctx: Context, email: string): Promise<api.MemberRow> {
  const wanted = email.trim().toLowerCase();
  const people = await listTeam(ctx);
  const found = people.find((one) => one.email.toLowerCase() === wanted);
  if (found === undefined) throw new UsageError(`nobody with the address ${email} in this org: \`pinecall team\` lists them`);
  return found;
}
