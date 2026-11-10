/** The numbers' doors: the org's numbers and what a call to one goes through, its carrier accounts, what they own, a number added, moved or let go, and the phone a person tests from. */

import { z } from "zod";

import { drop, GatewayError, post, put, read, type Credentials } from "@pinecall/core/api";

const named = encodeURIComponent;

const RouteSchema = z.looseObject({
  agent: z.string(),
  channel: z.enum(["phone", "web", "whatsapp"]),
  number: z.string().nullable(),
  env: z.enum(["production", "sandbox"]),
  /** Bought on the platform's own account. */
  managed: z.boolean().default(false),
});

/** What a call to a number does now: reaches the agent, waits on somebody, or stops. */
const RingsSchema = z.enum(["ok", "waiting", "broken"]);
export type Rings = z.infer<typeof RingsSchema>;

const NumberSchema = z.looseObject({
  route: RouteSchema,
  /** Who wrote the row: bought here, imported from an account, pointed here by the org, or typed by the operator. */
  origin: z.enum(["bought", "imported", "hooked", "typed"]).default("imported"),
  rings: RingsSchema.default("ok"),
  last_call_at: z.number().nullish(),
  via: z.string().nullish(),
  account: z.string().nullish(),
});
export type NumberRow = z.infer<typeof NumberSchema>;

const PathSchema = z.looseObject({
  number: z.string(),
  steps: z.array(z.looseObject({ step: z.enum(["carrier", "fence", "world", "agent"]), state: RingsSchema, says: z.string(), fix: z.string().nullish() })),
  rings: RingsSchema,
  last_call_at: z.number().nullish(),
});
export type NumberPath = z.infer<typeof PathSchema>;

const CatalogSchema = z.looseObject({
  /** The carriers this deployment admits: `automatic` through its API, `guided` through its portal. */
  carriers: z.array(z.looseObject({ kind: z.string(), name: z.string(), how: z.enum(["automatic", "guided"]) })),
  /** Whether the platform sells numbers. */
  sells: z.boolean(),
  /** The SIP name a carrier or a PBX sends this environment's calls to, on port 5060; a gateway from before it said has none. */
  sip_domain: z.string().nullish(),
});
export type Catalog = z.infer<typeof CatalogSchema>;

const CarrierSchema = z.looseObject({
  kind: z.enum(["twilio", "sip", "whatsapp"]),
  account: z.string(),
  label: z.string().default(""),
  networks: z.array(z.looseObject({ network: z.string(), state: z.enum(["waiting", "approved", "refused"]) })).default([]),
});
export type Carrier = z.infer<typeof CarrierSchema>;

const AvailableSchema = z.looseObject({
  numbers: z.array(z.looseObject({ number: z.string(), name: z.string(), imported: z.boolean(), held_elsewhere: z.boolean().default(false), account: z.string().optional() })),
});
export type Owned = z.infer<typeof AvailableSchema>["numbers"][number];

/** What adding a number answers: the route, and each thing done to make it ring, in the gateway's words. */
const WiredSchema = z.looseObject({ route: RouteSchema, steps: z.array(z.string()), dry_run: z.boolean() });
export type Wired = z.infer<typeof WiredSchema>;

export type WantedCarrier =
  | { kind: "twilio"; account_sid: string; user: string; secret: string; label?: string }
  | { kind: "sip"; username: string; password: string; addresses: string[]; outbound_host?: string; label?: string }
  | { kind: "whatsapp"; phone_number_id: string; access_token: string; label?: string };

export interface WantedNumber {
  number: string;
  agent: string;
  channel: "phone" | "whatsapp";
  /** The account the number lives in. */
  account?: string;
  /** The org points the number here itself: nothing outside is touched. */
  hooked?: boolean;
  /** A hooked number's carrier, of the catalog. */
  via?: string;
}

export interface WantedPurchase {
  country: string;
  area_code?: string;
  agent: string;
  channel: "phone";
}

const isStatus = (failed: unknown, ...statuses: number[]): boolean => failed instanceof GatewayError && statuses.includes(failed.status);

export async function readNumbers(credentials: Credentials): Promise<NumberRow[]> {
  return z.array(NumberSchema).parse(await read(credentials, "/v1/numbers"));
}

export async function readPath(credentials: Credentials, number: string): Promise<NumberPath> {
  return PathSchema.parse(await read(credentials, `/v1/numbers/${named(number)}/path`));
}

export async function readCatalog(credentials: Credentials): Promise<Catalog> {
  return CatalogSchema.parse(await read(credentials, "/v1/carriers/catalog"));
}

export async function readCarriers(credentials: Credentials): Promise<Carrier[]> {
  return z.looseObject({ carriers: z.array(CarrierSchema) }).parse(await read(credentials, "/v1/carriers")).carriers;
}

/** Keep an account of the org's, or the same account with a new secret; a Twilio pair is checked with Twilio. */
export async function bringCarrier(credentials: Credentials, wanted: WantedCarrier): Promise<void> {
  await put(credentials, "/v1/carrier", wanted);
}

/** What the org's accounts own, each with its account; none when it holds no account. */
export async function readOwned(credentials: Credentials): Promise<Owned[]> {
  try {
    return AvailableSchema.parse(await read(credentials, "/v1/numbers/available")).numbers;
  } catch (failed) {
    if (isStatus(failed, 404, 409)) return [];
    throw failed;
  }
}

/** Add a number; `dryRun` answers what would be done and writes nothing. */
export async function addNumber(credentials: Credentials, wanted: WantedNumber, dryRun: boolean): Promise<Wired> {
  return WiredSchema.parse(await post(credentials, `/v1/numbers${dryRun ? "?dry_run=true" : ""}`, wanted));
}

/** Buy a number on the platform's account; `dryRun` finds one and buys nothing. */
export async function buyNumber(credentials: Credentials, wanted: WantedPurchase, dryRun: boolean): Promise<Wired> {
  return WiredSchema.parse(await post(credentials, `/v1/numbers/buy${dryRun ? "?dry_run=true" : ""}`, wanted));
}

/** Let the number go: its route and its admission; the account that owns it keeps it. */
export async function releaseNumber(credentials: Credentials, number: string): Promise<void> {
  await drop(credentials, `/v1/numbers/${named(number)}`);
}

export async function moveNumber(credentials: Credentials, number: string, env: "production" | "sandbox"): Promise<void> {
  await put(credentials, `/v1/numbers/${named(number)}/env`, { env });
}

// ── the phone a person tests from ──

const LineSchema = z.looseObject({
  /** The person's own phone, or none. */
  calling: z.array(z.string()),
  /** The agent a call from it reaches; null, the one agent the org holds. */
  agent: z.string().nullable().optional(),
  /** The platform's own sandbox number to dial; null where it has none. */
  test_line: z.string().nullable().optional(),
});
export type Line = z.infer<typeof LineSchema>;

// A phone is said in the sandbox, whichever world the page is: it is a sandbox copy a call reaches.
const sandbox = (credentials: Credentials): Credentials => ({ ...credentials, world: "sandbox" });

/** The person's phone and the test line, or null for a key that is nobody's own (it has no phone to say). */
export async function readLine(credentials: Credentials): Promise<Line | null> {
  try {
    return LineSchema.parse(await read(sandbox(credentials), "/v1/line/numbers"));
  } catch (failed) {
    if (isStatus(failed, 403, 404, 409)) return null;
    throw failed;
  }
}

/** This phone is the person's own: a call from it reaches their copy of the agent named. */
export async function sayPhone(credentials: Credentials, number: string, agent: string): Promise<Line> {
  return LineSchema.parse(await put(sandbox(credentials), "/v1/line/from", { number, agent }));
}

export async function forgetPhone(credentials: Credentials): Promise<void> {
  await drop(sandbox(credentials), "/v1/line/from");
}

/** How many numbers the org may still buy here: null where the door says no limit, or says nothing. */
export async function readStock(credentials: Credentials): Promise<{ used: number; limit: number | null } | null> {
  const limits = z.looseObject({ numbers: z.looseObject({ used: z.number(), limit: z.number().nullable() }).optional() }).parse(await read(credentials, "/v1/limits"));
  return limits.numbers ?? null;
}
