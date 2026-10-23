/** The telephony endpoints: the org's numbers and routes, its carrier accounts, an agent's line, the callbacks waiting. */

import type { TheLine } from "@pinecall/agents/wire";

import { seg, type Env, type GatewayClient, type Query } from "./client.js";

export type { TheLine };

/** One route of the org: the number (none for a web channel), the agent it reaches, in which env. */
export interface NumberRoute {
  org: string;
  agent: string;
  channel: string;
  number: string | null;
  env: Env;
  /** Bought by the deployment on its own account, so it counts against the org's `numbers` limit. */
  managed: boolean;
}

/** How a route was written: bought here, imported off the org's account, hooked by a carrier, typed by hand. */
export type RouteOrigin = "bought" | "imported" | "hooked" | "typed";

/** One row of `GET /v1/numbers`: the route, how it was written, and the org's account it lives in. */
export interface NumberRow {
  route: NumberRoute;
  origin: RouteOrigin;
  /** What a call to it does now, read off the tables. */
  rings: "ok" | "waiting" | "broken";
  last_call_at: number | null;
  via: string | null;
  account: string | null;
}

/** One number an account owns, and whether this env imported it. */
export interface OwnedNumber {
  number: string;
  name: string;
  imported: boolean;
  /** Routed by another org of this deployment: not importable here until that org lets it go. */
  held_elsewhere: boolean;
  account: string;
}

/** `GET /v1/numbers/available`: what the org's Twilio accounts own; a SIP peer lists none. */
export interface AvailableNumbers {
  kind: string;
  numbers: OwnedNumber[];
}

/** `POST /v1/numbers` and `/v1/numbers/buy`: the route, one sentence a step, whether it ran. */
export interface NumberPlan {
  route: NumberRoute;
  steps: string[];
  dry_run: boolean;
}

/** `POST /v1/numbers`: a number an account of the org owns, pointed at an agent. */
export interface NumberImport {
  number: string;
  agent: string;
  account?: string;
  channel?: string;
}

/** `POST /v1/numbers/buy`: a number bought on the deployment's own account, pointed at an agent. */
export interface NumberPurchase {
  country: string;
  agent: string;
  area_code?: string;
  channel?: string;
}

/** A network a SIP peer calls from, and whether Pinecall's operator admitted it. */
export interface Network {
  network: string;
  state: string;
}

/** One account as `GET /v1/carrier` answers it: named, never its secret. */
export interface Carrier {
  kind: string;
  account: string;
  label: string;
  networks: Network[];
}

/** `PUT /v1/carrier`: one of the three kinds, its secret inside; the gateway seals it and never reads it back. */
export type CarrierBody =
  | { kind: "twilio"; account_sid: string; user: string; secret: string; label?: string }
  | {
      kind: "sip";
      username: string;
      password: string;
      addresses: string[];
      outbound_host?: string;
      outbound_transport?: string;
      outbound_username?: string;
      outbound_password?: string;
      label?: string;
    }
  | { kind: "whatsapp"; phone_number_id: string; access_token: string; label?: string };

/** One call back somebody asked for, as the org's list shows it. */
export interface Callback {
  position: number;
  agent: string;
  ts: number;
  channel: string;
  number: string;
  via: "overflow" | "widget" | "agent";
  call: string | null;
  when?: string | null;
}

/** `GET /v1/callbacks`: one page, oldest first, and the cursor the next starts at. */
export interface CallbackPage {
  requests: Callback[];
  next: number | null;
}

export function listNumbers(gw: GatewayClient): Promise<NumberRow[]> {
  return gw.get<NumberRow[]>("/v1/numbers");
}

export function listAvailableNumbers(gw: GatewayClient, account?: string): Promise<AvailableNumbers> {
  return gw.get<AvailableNumbers>("/v1/numbers/available", { account });
}

export function importNumber(gw: GatewayClient, body: NumberImport, dryRun: boolean): Promise<NumberPlan> {
  return gw.post<NumberPlan>("/v1/numbers", body, dryRunQuery(dryRun));
}

export function buyNumber(gw: GatewayClient, body: NumberPurchase, dryRun: boolean): Promise<NumberPlan> {
  return gw.post<NumberPlan>("/v1/numbers/buy", body, dryRunQuery(dryRun));
}

export async function deleteNumber(gw: GatewayClient, number: string): Promise<void> {
  await gw.delete(`/v1/numbers/${seg(number)}`);
}

/** Every route of every agent in this env: org data, which the `app` scope lets a server token read too. */
export function listRoutes(gw: GatewayClient): Promise<NumberRoute[]> {
  return gw.get<NumberRoute[]>("/v1/routes");
}

export async function listCarriers(gw: GatewayClient): Promise<Carrier[]> {
  return (await gw.get<{ carriers: Carrier[] }>("/v1/carriers")).carriers;
}

/** The org's only account, or the one named. */
export function getCarrier(gw: GatewayClient, account?: string): Promise<Carrier> {
  return gw.get<Carrier>("/v1/carrier", { account });
}

export function putCarrier(gw: GatewayClient, body: CarrierBody): Promise<Carrier> {
  return gw.put<Carrier>("/v1/carrier", body);
}

export async function deleteCarrier(gw: GatewayClient, account?: string): Promise<void> {
  await gw.delete("/v1/carrier", { account });
}

export function getLine(gw: GatewayClient, slug: string): Promise<TheLine> {
  return gw.get<TheLine>(linePath(slug));
}

export function claimLine(gw: GatewayClient, slug: string): Promise<TheLine> {
  return gw.post<TheLine>(linePath(slug));
}

export function releaseLine(gw: GatewayClient, slug: string): Promise<TheLine> {
  return gw.delete<TheLine>(linePath(slug));
}

/** Per person, not per agent: one phone covers every agent they run. */
export function setCallerNumber(gw: GatewayClient, number: string): Promise<{ calling: string[] }> {
  return gw.put<{ calling: string[] }>("/v1/line/from", { number });
}

export function deleteCallerNumber(gw: GatewayClient): Promise<{ forgot: string[] }> {
  return gw.delete<{ forgot: string[] }>("/v1/line/from");
}

export function listCallbacks(gw: GatewayClient, query: { agent?: string | undefined; after?: number | undefined }): Promise<CallbackPage> {
  return gw.get<CallbackPage>("/v1/callbacks", query);
}

function linePath(slug: string): string {
  return `/v1/agents/${seg(slug)}/line`;
}

function dryRunQuery(dryRun: boolean): Query | undefined {
  return dryRun ? { dry_run: true } : undefined;
}
