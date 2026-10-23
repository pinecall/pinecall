/** Telephony: the org's numbers and routes, its carrier accounts, whose terminal an agent's number rings in, and the callbacks waiting. */

import { z } from "zod";

import * as accounts from "../accounts/service/index.js";
import * as api from "../api/telephony.js";
import * as billing from "../billing/service.js";
import type { Context } from "../context.js";
import { UsageError } from "../errors.js";

export type { AvailableNumbers, Callback, CallbackPage, Carrier, CarrierBody, NumberPlan, NumberRoute, NumberRow, OwnedNumber, TheLine } from "../api/telephony.js";

// The gateway's sentence when the org holds several accounts and the import named none.
export const SEVERAL_ACCOUNTS = "name one of them";
export const NAME_THE_ACCOUNT = "  name the account that owns the number: --account <id> (`pinecall carriers list`)";

const E164 = /^\+[1-9]\d{6,14}$/;

/** What `numbers import` takes: a number an account of the org owns, pointed at an agent. */
export const ImportNumberInput = z.object({
  number: z.string().regex(E164, "a number is +E.164: +34910000000"),
  agent: z.string().min(1),
  account: z.string().min(1).optional(),
  channel: z.enum(["phone", "whatsapp"]).optional(),
  move: z.boolean().default(false),
  dryRun: z.boolean().default(false),
});
export type ImportNumberInput = z.infer<typeof ImportNumberInput>;

/** What `numbers buy` takes: a country (and area code) on the deployment's own account, pointed at an agent. */
export const BuyNumberInput = z.object({
  country: z.string().length(2).transform((code) => code.toUpperCase()),
  agent: z.string().min(1),
  areaCode: z.string().regex(/^\d+$/).optional(),
  channel: z.enum(["phone", "whatsapp"]).optional(),
  dryRun: z.boolean().default(false),
});
export type BuyNumberInput = z.infer<typeof BuyNumberInput>;

/** What `carriers add` takes: one of the three kinds, its fields; the secrets come apart, off stdin. */
export const AddCarrierInput = z.discriminatedUnion("kind", [
  z.object({ kind: z.literal("twilio"), accountSid: z.string().min(1), user: z.string().min(1), label: z.string().optional() }),
  z.object({
    kind: z.literal("sip"),
    username: z.string().min(1),
    addresses: z.array(z.string().min(1)).min(1),
    outboundHost: z.string().optional(),
    outboundTransport: z.enum(["auto", "udp", "tcp", "tls"]).optional(),
    outboundUsername: z.string().optional(),
    label: z.string().optional(),
  }),
  z.object({ kind: z.literal("whatsapp"), phoneNumberId: z.string().min(1), label: z.string().optional() }),
]);
export type AddCarrierInput = z.infer<typeof AddCarrierInput>;

/** What `callbacks` takes: one agent's, and where the page before ended. */
export const ListCallbacksInput = z.object({
  agent: z.string().min(1).optional(),
  after: z.number().int().min(0).optional(),
});
export type ListCallbacksInput = z.infer<typeof ListCallbacksInput>;

/** A number bought (or planned): the steps, and how many bought numbers the env holds of how many. */
export interface NumberBought extends api.NumberPlan {
  stock: billing.Limit;
}

/** One carrier account with how many numbers it routes in this env. */
export interface CarrierListed extends api.Carrier {
  routed: number;
}

/** The secrets an account takes, in order: [what the prompt names, the body's field]. */
export function secretsOf(input: AddCarrierInput): [string, string][] {
  if (input.kind === "twilio") return [["Twilio secret (the API key's, or the auth token)", "secret"]];
  if (input.kind === "whatsapp") return [["WhatsApp access token", "access_token"]];
  const secrets: [string, string][] = [["SIP password", "password"]];
  if (input.outboundUsername !== undefined) secrets.push(["outbound password", "outbound_password"]);
  return secrets;
}

export async function listNumbers(ctx: Context): Promise<api.NumberRow[]> {
  return api.listNumbers(ctx.gateway());
}

export async function listAvailableNumbers(ctx: Context, account?: string): Promise<api.AvailableNumbers> {
  return api.listAvailableNumbers(ctx.gateway(), account);
}

/** A number an account of the org owns, pointed at an agent; a dry run answers the steps and writes nothing. */
export async function importNumber(ctx: Context, input: ImportNumberInput): Promise<api.NumberPlan> {
  const body: api.NumberImport = { number: input.number, agent: input.agent };
  if (input.account !== undefined) body.account = input.account;
  if (input.channel !== undefined) body.channel = input.channel;
  return api.importNumber(ctx.gateway(), body, input.dryRun);
}

/** A number bought on the deployment's own account and pointed at an agent; it counts against the org's `numbers` limit. */
export async function buyNumber(ctx: Context, input: BuyNumberInput): Promise<NumberBought> {
  const body: api.NumberPurchase = { country: input.country, agent: input.agent };
  if (input.areaCode !== undefined) body.area_code = input.areaCode;
  if (input.channel !== undefined) body.channel = input.channel;
  const planned = await api.buyNumber(ctx.gateway(), body, input.dryRun);
  const { limits } = await billing.getLimits(ctx);
  return { ...planned, stock: limits.numbers };
}

/** The route forgotten and the number off the SFU trunk; the carrier account keeps it. */
export async function dropNumber(ctx: Context, number: string): Promise<{ number: string }> {
  await api.deleteNumber(ctx.gateway(), number);
  return { number };
}

/** Every route of every agent in this env. */
export async function listRoutes(ctx: Context): Promise<api.NumberRoute[]> {
  return api.listRoutes(ctx.gateway());
}

/** Every account of the org, oldest first, with how many numbers each routes in this env. */
export async function listCarriers(ctx: Context): Promise<CarrierListed[]> {
  const gw = ctx.gateway();
  const carriers = await api.listCarriers(gw);
  if (carriers.length === 0) return [];
  const routed = await api.listNumbers(gw);
  return carriers.map((row) => ({ ...row, routed: routed.filter((number) => number.account === row.account).length }));
}

/** The org's only account, or the one named. */
export async function showCarrier(ctx: Context, account?: string): Promise<api.Carrier> {
  return api.getCarrier(ctx.gateway(), account);
}

/** An account kept, its secrets by the field each fills; the same account again replaces its secret. */
export async function addCarrier(ctx: Context, input: AddCarrierInput, secrets: Record<string, string>): Promise<api.Carrier> {
  for (const [name, field] of secretsOf(input)) {
    if ((secrets[field] ?? "").trim() === "") throw new UsageError(`no ${name} was given: nothing was kept`);
  }
  return api.putCarrier(ctx.gateway(), carrierBodyOf(input, secrets));
}

/** An account forgotten; its numbers stay routed until each is dropped. */
export async function dropCarrier(ctx: Context, account?: string): Promise<{ account: string | undefined }> {
  await api.deleteCarrier(ctx.gateway(), account);
  return { account };
}

/** Who is answering this agent's number right now, and who else is running it. */
export async function showLine(ctx: Context, choice: { agent?: string | undefined; file?: string | undefined }): Promise<api.TheLine> {
  return api.getLine(ctx.gateway(), ctx.slug("line", choice));
}

export async function claimLine(ctx: Context, choice: { agent?: string | undefined; file?: string | undefined }): Promise<api.TheLine> {
  return api.claimLine(ctx.gateway(), ctx.slug("line claim", choice));
}

export async function releaseLine(ctx: Context, choice: { agent?: string | undefined; file?: string | undefined }): Promise<api.TheLine> {
  return api.releaseLine(ctx.gateway(), ctx.slug("line release", choice));
}

/** The person's own phone, said to the gateway and kept on this machine, so every `start` says it again. */
export async function setCallerNumber(ctx: Context, number: string): Promise<{ calling: string[] }> {
  if (!E164.test(number)) throw new UsageError(`a number is +E.164: +34600000000, not ${number}`);
  const gw = ctx.gateway();
  const said = await api.setCallerNumber(gw, number);
  accounts.writeCallerNumber(accounts.homeOf(ctx.processEnv), gw.url, number);
  return said;
}

export async function forgetCallerNumber(ctx: Context): Promise<{ forgot: string[] }> {
  const gw = ctx.gateway();
  const said = await api.deleteCallerNumber(gw);
  accounts.writeCallerNumber(accounts.homeOf(ctx.processEnv), gw.url, undefined);
  return said;
}

/** The phone this machine said was the person's at this gateway, re-sent by `start`; failures are the caller's to ignore. */
export async function resendCallerNumber(ctx: Context): Promise<void> {
  const gw = ctx.gateway();
  const kept = accounts.readCallerNumber(accounts.homeOf(ctx.processEnv), gw.url);
  if (kept !== undefined) await api.setCallerNumber(gw, kept);
}

export async function listCallbacks(ctx: Context, input: ListCallbacksInput): Promise<api.CallbackPage> {
  return api.listCallbacks(ctx.gateway(), { agent: input.agent, after: input.after });
}

function carrierBodyOf(input: AddCarrierInput, secrets: Record<string, string>): api.CarrierBody {
  const label = input.label === undefined ? {} : { label: input.label };
  if (input.kind === "twilio") return { kind: "twilio", account_sid: input.accountSid, user: input.user, secret: secrets["secret"]!.trim(), ...label };
  if (input.kind === "whatsapp") return { kind: "whatsapp", phone_number_id: input.phoneNumberId, access_token: secrets["access_token"]!.trim(), ...label };
  return {
    kind: "sip",
    username: input.username,
    password: secrets["password"]!.trim(),
    addresses: input.addresses,
    ...(input.outboundHost === undefined ? {} : { outbound_host: input.outboundHost }),
    ...(input.outboundTransport === undefined ? {} : { outbound_transport: input.outboundTransport }),
    ...(input.outboundUsername === undefined ? {} : { outbound_username: input.outboundUsername, outbound_password: secrets["outbound_password"]!.trim() }),
    ...label,
  };
}
