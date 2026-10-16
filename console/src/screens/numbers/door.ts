/** Numbers doors: the org's numbers and their path, its accounts, the catalog, import, purchase, release and outbound. */

import { z } from "zod";

import { drop, post, put, read, type Credentials } from "@pinecall/core/api";

const RouteSchema = z.object({
  org: z.string(),
  agent: z.string(),
  channel: z.enum(["phone", "web", "whatsapp"]),
  number: z.string().nullable(),
  label: z.string().nullable(),
  env: z.enum(["production", "sandbox"]),
  managed: z.boolean().default(false),
});

/** What a call to a number does now: works, waits on someone, or stops (runtime `StepState`). */
const RingsSchema = z.enum(["ok", "waiting", "broken"]);
export type Rings = z.infer<typeof RingsSchema>;

// Runtime wire/rest/numbers.py `NumberRow`. `managed` means the box bought it; `origin` who wrote the row.
const AnsweringSchema = z.object({
  route: RouteSchema,
  origin: z.enum(["bought", "imported", "hooked", "typed"]).default("imported"),
  rings: RingsSchema.default("ok"),
  last_call_at: z.number().nullish(),
  via: z.string().nullish(),
  account: z.string().nullish(),
});
export type Answering = z.infer<typeof AnsweringSchema>;

// Runtime `NumberPath`: the four steps of a call's way to its agent, each with what would fix it.
const PathSchema = z.object({
  number: z.string(),
  steps: z.array(z.object({ step: z.enum(["carrier", "fence", "world", "agent"]), state: RingsSchema, says: z.string(), fix: z.string().nullish() })),
  rings: RingsSchema,
  last_call_at: z.number().nullish(),
});
export type NumberPath = z.infer<typeof PathSchema>;

// Runtime `CarrierCatalog`: the carriers this box admits, automatic (its API) or guided (SIP terms).
const CatalogSchema = z.object({
  carriers: z.array(z.object({ kind: z.string(), name: z.string(), how: z.enum(["automatic", "guided"]), networks: z.array(z.string()) })),
  sells: z.boolean(),
});
export type Catalog = z.infer<typeof CatalogSchema>;

/** The kinds of account an org holds: a Twilio account, a SIP peer, a WhatsApp number at Meta. */
export type CarrierKind = "twilio" | "sip" | "whatsapp";

// GET /v1/carrier and /v1/carriers: kind, account and label, never a secret; a peer's networks and the operator's answer.
const CarrierSchema = z.object({
  kind: z.enum(["twilio", "sip", "whatsapp"]),
  account: z.string(),
  label: z.string().default(""),
  networks: z.array(z.object({ network: z.string(), state: z.enum(["waiting", "approved", "refused"]) })).default([]),
});
export type Carrier = z.infer<typeof CarrierSchema>;
const CarriersSchema = z.object({ carriers: z.array(CarrierSchema) });

const AvailableSchema = z.object({
  kind: z.string(),
  numbers: z.array(z.object({ number: z.string(), name: z.string(), imported: z.boolean(), account: z.string().optional() })),
});
export type Available = z.infer<typeof AvailableSchema>;

// Shared by import and purchase. With `?dry_run=true` nothing is written.
const WiredSchema = z.object({
  route: RouteSchema,
  steps: z.array(z.string()),
  dry_run: z.boolean(),
});
export type Wired = z.infer<typeof WiredSchema>;

/** PUT /v1/carrier body: one more account of the org, or the same account with a new secret. */
export type WantedCarrier =
  | { kind: "twilio"; account_sid: string; user: string; secret: string; label?: string }
  | {
      kind: "sip";
      username: string;
      password: string;
      addresses: string[];
      /** Outbound destination; omit for a receive-only peer. */
      outbound_host?: string;
      outbound_transport?: "auto" | "udp" | "tcp" | "tls";
      outbound_username?: string;
      outbound_password?: string;
      label?: string;
    }
  | { kind: "whatsapp"; phone_number_id: string; access_token: string; label?: string };

/** POST /v1/numbers body: a number of one of the org's accounts, or one the org points here itself. */
export interface WantedNumber {
  number: string;
  agent: string;
  channel: "phone" | "whatsapp";
  /** The account the number lives in; needed when the org holds several. */
  account?: string;
  /** The org points the number at the gateway itself: nothing outside is touched. */
  hooked?: boolean;
  /** A self-hooked number's own networks, which the box's operator approves. */
  networks?: string[];
  /** A self-hooked number's carrier from the box's catalog; Twilio's networks when unsaid. */
  via?: string;
}

export interface WantedPurchase {
  country: string;
  area_code?: string;
  agent: string;
  channel: "phone" | "whatsapp";
}

/** The org's routes in this world, in worker order. */
export async function readNumbers(credentials: Credentials): Promise<Answering[]> {
  return z.array(AnsweringSchema).parse(await read(credentials, "/v1/numbers"));
}

/** What a call to the number goes through now, step by step. */
export async function readPath(credentials: Credentials, number: string): Promise<NumberPath> {
  return PathSchema.parse(await read(credentials, `/v1/numbers/${encodeURIComponent(number)}/path`));
}

/** The carriers this box admits, and whether it sells numbers. */
export async function readCatalog(credentials: Credentials): Promise<Catalog> {
  return CatalogSchema.parse(await read(credentials, "/v1/carriers/catalog"));
}

/** Move a number into the other world: its row and the two rules. */
export async function moveNumber(credentials: Credentials, number: string, env: "production" | "sandbox"): Promise<void> {
  await put(credentials, `/v1/numbers/${encodeURIComponent(number)}/env`, { env });
}

/** Every account of the org, oldest first; a gateway that lists none answers the one it knows. */
export async function readCarriers(credentials: Credentials): Promise<Carrier[]> {
  try {
    return CarriersSchema.parse(await read(credentials, "/v1/carriers")).carriers;
  } catch (refused) {
    if (!isStatus(refused, 404) && !isStatus(refused, 405)) throw refused;
  }
  try {
    return [CarrierSchema.parse(await read(credentials, "/v1/carrier"))];
  } catch (refused) {
    if (isStatus(refused, 404)) return [];
    throw refused;
  }
}

/** Add an account, or replace the secret of one the org holds. A Twilio pair is verified. */
export async function bringCarrier(credentials: Credentials, wanted: WantedCarrier): Promise<void> {
  await put(credentials, "/v1/carrier", wanted);
}

/** Forget an account. Its numbers stay routed until released. */
export async function dropCarrier(credentials: Credentials, account: string): Promise<void> {
  await drop(credentials, `/v1/carrier?account=${encodeURIComponent(account)}`);
}

/** What the org's accounts own, each number with its account. A SIP peer lists none. */
export async function readAvailable(credentials: Credentials): Promise<Available> {
  return AvailableSchema.parse(await read(credentials, "/v1/numbers/available"));
}

/** Import a number; `dryRun` returns the plan only. */
export async function importNumber(credentials: Credentials, wanted: WantedNumber, dryRun: boolean): Promise<Wired> {
  return WiredSchema.parse(await post(credentials, `/v1/numbers${dryRun ? "?dry_run=true" : ""}`, wanted));
}

/** Buy a number on the box's carrier; `dryRun` returns the plan without purchasing. */
export async function buyNumber(credentials: Credentials, wanted: WantedPurchase, dryRun: boolean): Promise<Wired> {
  return WiredSchema.parse(await post(credentials, `/v1/numbers/buy${dryRun ? "?dry_run=true" : ""}`, wanted));
}

/** Release a number's route and admission; the account is untouched. */
export async function releaseNumber(credentials: Credentials, number: string): Promise<void> {
  await drop(credentials, `/v1/numbers/${encodeURIComponent(number)}`);
}

// GET /v1/carrier/outbound (runtime console-api.md §4). Loose so guards added later don't fail parsing.
const OutboundSchema = z.looseObject({
  ready: z.boolean(),
  kind: z.string().nullish(),
  from_numbers: z.array(z.string()),
  steps_missing: z.array(z.string()),
  guards: z.looseObject({
    dial_anywhere: z.boolean(),
    per_minute: z.number(),
    per_day: z.number(),
    max_duration_s: z.number(),
  }),
});
export type Outbound = z.infer<typeof OutboundSchema>;

const ProvisionedSchema = z.looseObject({ steps: z.array(z.string()), dry_run: z.boolean(), ready: z.boolean() });
export type Provisioned = z.infer<typeof ProvisionedSchema>;

function viaAccount(account: string | undefined, dryRun = false): string {
  const params = new URLSearchParams();
  if (account !== undefined) params.set("account", account);
  if (dryRun) params.set("dry_run", "true");
  const query = params.toString();
  return query === "" ? "" : `?${query}`;
}

/** Outbound readiness through one account, or null on 404 or when the key may not ask. */
export async function readOutbound(credentials: Credentials, account?: string): Promise<Outbound | null> {
  try {
    return OutboundSchema.parse(await read(credentials, `/v1/carrier/outbound${viaAccount(account)}`));
  } catch (refused) {
    if (isStatus(refused, 404) || isStatus(refused, 405) || isStatus(refused, 403)) return null;
    throw refused;
  }
}

/** Provision or repair outbound through one account; `dryRun` returns the plan only. */
export async function provisionOutbound(credentials: Credentials, dryRun: boolean, account?: string): Promise<Provisioned> {
  return ProvisionedSchema.parse(await post(credentials, `/v1/carrier/outbound${viaAccount(account, dryRun)}`, {}));
}

const DialledSchema = z.looseObject({ call: z.string() });

/** Place a call as the agent (POST /v1/agents/{slug}/dial); resolves to the call. */
export async function dial(credentials: Credentials, agent: string, to: string, from?: string): Promise<string> {
  const body = from === undefined || from === "" ? { to } : { to, from };
  return DialledSchema.parse(await post(credentials, `/v1/agents/${encodeURIComponent(agent)}/dial`, body)).call;
}

function isStatus(failed: unknown, status: number): boolean {
  return typeof failed === "object" && failed !== null && (failed as { status?: unknown }).status === status;
}
