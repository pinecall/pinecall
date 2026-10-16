/** An agent's calls: the list, one call whole with what it cost and how it was judged, and its log a page at a time. */

import { z } from "zod";

import * as api from "../../api/calls.js";
import type { Context } from "../../context.js";
import { GatewayError, UsageError } from "../../errors.js";

export type { CallState, Entry, EntryPage, SessionLine } from "../../api/calls.js";

/** The page a log is read in when `--limit` is left out. */
export const A_PAGE = 200;
const A_HUNDRED = { error: "--limit takes a whole number from 1 to 100" };
const A_PAGE_LIMIT = { error: `--limit takes a whole number from 1 to ${api.PAGE_MOST}` };

// Filtered server-side, so `show` is usually a single request; at most PAGES pages (about an hour of call).
const THE_ENDING = ["call.summary", "call.score"];
const PAGES = 6;

export const NO_SUCH_CALL = (call: string): string => `no call ${call} on this gateway: \`pinecall sessions\` names the ones there are`;

/** What `sessions` takes with no call named: the agent, and how many calls, newest first. */
export const ListSessionsInput = z.object({
  agent: z.string().min(1).optional(),
  limit: z.number(A_HUNDRED).int(A_HUNDRED).min(1, A_HUNDRED).max(100, A_HUNDRED).optional(),
});
export type ListSessionsInput = z.infer<typeof ListSessionsInput>;

/** What `sessions log` takes: the call, the cursor, the page's size, the types kept. */
export const ReadLogInput = z.object({
  call: z.string().min(1),
  after: z.number().int().min(0).default(0),
  limit: z.number(A_PAGE_LIMIT).int(A_PAGE_LIMIT).min(1, A_PAGE_LIMIT).max(api.PAGE_MOST, A_PAGE_LIMIT).default(A_PAGE),
  types: z.array(z.string().min(1)).optional(),
});
export type ReadLogInput = z.infer<typeof ReadLogInput>;

/** One call whole: whether it is live, its summary and its score as the log holds them. */
export interface CallShown {
  call: string;
  live: boolean;
  summary: Record<string, unknown> | undefined;
  score: Record<string, unknown> | undefined;
}

/** One page of a call's log: the entries, the seq to read on from (null once there is nothing after it), whether the call is live. */
export interface LogPage {
  call: string;
  entries: api.Entry[];
  next: number | null;
  live: boolean;
}

export async function listSessions(ctx: Context, input: ListSessionsInput): Promise<{ agent: string; calls: api.SessionLine[] }> {
  const agent = ctx.slug("sessions", { agent: input.agent });
  return { agent, calls: await api.listSessions(ctx.gateway(), agent, input.limit) };
}

/** The call's state; an unknown id is a usage error naming it, so a typo is visible. */
export async function callState(ctx: Context, call: string): Promise<api.CallState> {
  try {
    return await api.getCallState(ctx.gateway(), call);
  } catch (failed) {
    if (failed instanceof GatewayError && failed.status === 404) throw new UsageError(NO_SUCH_CALL(call));
    throw failed;
  }
}

/** One call whole: its summary and score read off the log; a live call has neither yet. */
export async function showCall(ctx: Context, call: string): Promise<CallShown> {
  // Checked first: the events endpoint returns an empty page for an unknown call id.
  const state = await callState(ctx, call);
  const found: Record<string, Record<string, unknown>> = {};
  let after = 0;
  for (let page = 0; page < PAGES; page += 1) {
    const read = await api.listCallEntries(ctx.gateway(), call, { types: THE_ENDING, after });
    for (const entry of read.entries) found[entry.type] = entry.data;
    if (read.next === null || read.next <= after) break;
    after = read.next;
  }
  return { call, live: state.live, summary: found["call.summary"], score: found["call.score"] };
}

/**
 * One page of a call's log. `next` is the gateway's: the last seq it READ, kept or not, so a page the
 * types narrowed to a few entries still moves the cursor past everything it skipped. It is null once
 * it reached the last seq of a call that is over.
 */
export async function readLog(ctx: Context, input: ReadLogInput): Promise<LogPage> {
  const state = await callState(ctx, input.call);
  const page = await api.listCallEntries(ctx.gateway(), input.call, { after: input.after, limit: input.limit, types: input.types });
  const next = page.next !== null && (state.live || page.next < state.lastSeq) ? page.next : null;
  return { call: input.call, entries: page.entries, next, live: state.live };
}
