/** The calls endpoints: an agent's calls, one call's state, its log paged or followed, the supervisor's verbs, a listen seat, the chat socket. */

import { observe } from "@pinecall/agents/client";
import type { SessionLine, Verb } from "@pinecall/agents/wire";

import { seg, type GatewayClient } from "./client.js";

export type { SessionLine, Verb } from "@pinecall/agents/wire";

/** One entry of a call's log as the events endpoint answers it. */
export interface Entry {
  seq: number;
  ts?: number;
  type: string;
  data: Record<string, unknown>;
  /** Call id; set on chat socket frames, optional on a single call's page. */
  call?: string | null;
}

/** One page of a call's log: the entries kept, and the last seq the gateway read, kept or not. */
export interface EntryPage {
  entries: Entry[];
  next: number | null;
}

/** What a page of the log is read with: the cursor, the page's size, the types kept. */
export interface EntryQuery {
  after?: number | undefined;
  limit?: number | undefined;
  types?: readonly string[] | undefined;
}

/** `GET /v1/calls/{call}/state`: whether the call is live, and its log's length. */
export interface CallState {
  live: boolean;
  lastSeq: number;
}

/** A listen seat: LiveKit connection fields and this terminal's identity in the room. */
export interface ListenSeat {
  server_url: string;
  participant_token: string;
  identity: string;
}

/** How a written call opens: which process serves it, who calls, who plays them, in what state. */
export interface ChatOpening {
  /** Pin the serving process; otherwise the gateway picks the newest socket holding the agent. */
  app?: string | undefined;
  /** The contact memory files the call under. */
  contact?: string | undefined;
  /** The simulated persona; the gateway records it on `call.started` for attribution. */
  persona?: string | undefined;
  /** The state the call opens in, carried on its `call.started`. */
  state?: Record<string, unknown> | undefined;
  /** A call to resume, after the gateway dropped the socket. */
  call?: string | undefined;
}

/** The most entries the events endpoint answers in one page. */
export const PAGE_MOST = 500;

export async function listSessions(gw: GatewayClient, agent: string, limit?: number): Promise<SessionLine[]> {
  return (await gw.get<{ calls: SessionLine[] }>(`/v1/agents/${seg(agent)}/sessions`, { limit })).calls;
}

/** The only endpoint that answers 404 for an unknown call; the events one returns an empty page. */
export async function getCallState(gw: GatewayClient, call: string): Promise<CallState> {
  const said = await gw.get<{ live?: boolean; last_seq?: number }>(`/v1/calls/${seg(call)}/state`);
  return { live: said.live === true, lastSeq: said.last_seq ?? 0 };
}

/** One page of a call's log; 204 (null) once the cursor is past the end of a call that is over. */
export async function listCallEntries(gw: GatewayClient, call: string, query: EntryQuery = {}): Promise<EntryPage> {
  const page = await gw.get<{ entries?: Entry[]; next?: number | null } | null>(`/v1/calls/${seg(call)}/events`, {
    after: query.after ?? 0,
    limit: query.limit ?? PAGE_MOST,
    types: query.types === undefined ? undefined : query.types.join(","),
  });
  return { entries: page?.entries ?? [], next: page?.next ?? null };
}

/** Each entry of a call's log (or the org's feed) from the cursor on, reconnecting by itself, until `signal` aborts. */
export async function* followEntries(gw: GatewayClient, target: { call: string } | { agent: string } | { feed: true }, query: EntryQuery & { onOpen?: () => void; signal?: AbortSignal } = {}): AsyncGenerator<Entry> {
  const options = {
    url: gw.url,
    apiKey: gw.key,
    env: gw.env,
    ...(query.after === undefined ? {} : { after: query.after }),
    ...(query.types === undefined ? {} : { types: query.types }),
    ...(query.onOpen === undefined ? {} : { onOpen: query.onOpen }),
    ...(query.signal === undefined ? {} : { signal: query.signal }),
  };
  for await (const seen of observe(target, options)) yield seen.entry as Entry;
}

/** One supervisor verb sent to a live call; it lands in the call's log as its own `supervisor.*` entry. */
export async function sendVerb(gw: GatewayClient, call: string, verb: Verb): Promise<void> {
  await gw.post(`/v1/calls/${seg(call)}/verbs`, verb);
}

/** `POST /v1/calls/{call}/listen` (scope `observe`): a hidden, silent seat in the call's room. */
export function createListenSeat(gw: GatewayClient, call: string): Promise<ListenSeat> {
  return gw.post<ListenSeat>(`/v1/calls/${seg(call)}/listen`, {});
}

/** The `/v1/chat` WebSocket URL: a written call at the agent, naming no app unless one is pinned. */
export function chatUrl(gw: GatewayClient, agent: string, opening: ChatOpening = {}): string {
  const url = new URL(gw.urlOf("/v1/chat"));
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.searchParams.set("agent", agent);
  // searchParams encodes each value: a raw `+` in a contact would arrive as a space.
  if (opening.app !== undefined) url.searchParams.set("app", opening.app);
  if (opening.contact !== undefined) url.searchParams.set("contact", opening.contact);
  if (opening.persona !== undefined) url.searchParams.set("persona", opening.persona);
  if (opening.state !== undefined) url.searchParams.set("state", JSON.stringify(opening.state));
  if (opening.call !== undefined) url.searchParams.set("call", opening.call);
  return url.toString();
}
