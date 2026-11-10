/** Box settings' doors: what a new organization gets, sign-in, the mailbox, the deployment's vendor keys, its numbers account, and the providers row. */

import { z } from "zod";

import { drop, GatewayError, post, put, read, type Credentials } from "@pinecall/core/api";

const OPS = "/v1/ops";
const named = encodeURIComponent;

// A door this gateway does not have answers null, never an error: the tab says so calmly.
async function orAbsent<T>(asking: Promise<T>): Promise<T | null> {
  try {
    return await asking;
  } catch (refused) {
    if (refused instanceof GatewayError && (refused.status === 404 || refused.status === 405)) return null;
    throw refused;
  }
}

// ── admission ──

export const WORLDS = ["sandbox", "production"] as const;
export type World = (typeof WORLDS)[number];

/** The limits by name, in the order the page lists them. null is no limit, zero refuses everything. */
export const QUOTAS = ["minutes", "messages", "llm_tokens", "concurrent_calls", "agents", "numbers", "seats", "hosted_apps", "memory_facts", "knowledge_chunks", "evals", "simulations", "budget_usd"] as const;
export type Quota = (typeof QUOTAS)[number];

/** How its simulations are shaped: null is the platform's own, never no limit. */
export const SHAPES = ["simulations_at_once", "comparison_calls"] as const;
export type Shape = (typeof SHAPES)[number];

// One environment's row: every limit by name beside `lends`; what the page does not draw rides along.
const NewbornSchema = z.looseObject({ lends: z.array(z.string()).nullish() });
export type Newborn = z.infer<typeof NewbornSchema>;

const AdmissionSchema = z.looseObject({
  first: z.record(z.string(), NewbornSchema),
  later: z.record(z.string(), NewbornSchema).nullish(),
});
export type Admission = z.infer<typeof AdmissionSchema>;

export async function readAdmission(credentials: Credentials): Promise<Admission> {
  return AdmissionSchema.parse(await read(credentials, `${OPS}/admission`));
}

/** The row replaced whole; the organizations already made keep what they have. */
export async function saveAdmission(credentials: Credentials, wanted: Admission): Promise<void> {
  await put(credentials, `${OPS}/admission`, wanted);
}

/** A limit as the row holds it: a number, or null for none. */
export function limitOf(row: Newborn | undefined, name: Quota | Shape): number | null {
  const held: unknown = row?.[name];
  return typeof held === "number" ? held : null;
}

// ── sign-in ──

const SignInSchema = z.looseObject({
  google: z.looseObject({ configured: z.boolean(), client_id: z.string().nullish(), redirect_uri: z.string().nullish() }),
});
export type SignIn = z.infer<typeof SignInSchema>;

export async function readSignIn(credentials: Credentials): Promise<SignIn | null> {
  return orAbsent(read(credentials, `${OPS}/signin`).then((said) => SignInSchema.parse(said)));
}

/** The OAuth client made at Google; its secret is sent once and never read back. */
export async function saveGoogle(credentials: Credentials, wanted: { client_id: string; client_secret: string }): Promise<void> {
  await put(credentials, `${OPS}/signin/google`, wanted);
}

export async function removeGoogle(credentials: Credentials): Promise<void> {
  await drop(credentials, `${OPS}/signin/google`);
}

// ── the mailbox ──

export const SECURITIES = ["starttls", "tls", "none"] as const;
export type Security = (typeof SECURITIES)[number];

const MailSchema = z.looseObject({
  configured: z.boolean(),
  /** `stored` when saved from this page, `environment` when the deployment was installed with one. */
  source: z.string().nullish(),
  host: z.string().nullish(),
  port: z.number().nullish(),
  security: z.string().nullish(),
  username: z.string().nullish(),
  from: z.string().nullish(),
  verified_at: z.string().nullish(),
  last_error: z.string().nullish(),
});
export type Mail = z.infer<typeof MailSchema>;

export interface WantedMail {
  host: string;
  port: number;
  security: Security;
  username: string | null;
  /** Write-only; left out, the gateway keeps the one it has. */
  password?: string;
  from: string;
}

export async function readMail(credentials: Credentials): Promise<Mail | null> {
  return orAbsent(read(credentials, `${OPS}/mail`).then((said) => MailSchema.parse(said)));
}

/** The stored mailbox replaced whole; saving sends nothing. */
export async function saveMail(credentials: Credentials, wanted: WantedMail): Promise<void> {
  await put(credentials, `${OPS}/mail`, wanted);
}

export async function removeMail(credentials: Credentials): Promise<void> {
  await drop(credentials, `${OPS}/mail`);
}

/** One real letter, waited for: whether the mail server took it, and its own words when it did not. */
export async function testMail(credentials: Credentials, to: string): Promise<{ sent: boolean; error: string | null }> {
  const said = z.looseObject({ sent: z.boolean(), error: z.string().nullish() }).parse(await post(credentials, `${OPS}/mail/test`, { to }));
  return { sent: said.sent, error: said.error ?? null };
}

// ── the deployment's vendor keys ──

/** The vendors the deployment holds a key for; never a key. */
export async function readHeldVendors(credentials: Credentials): Promise<string[]> {
  return z.looseObject({ vendors: z.array(z.string()) }).parse(await read(credentials, `${OPS}/provider-keys`)).vendors;
}

/** Hold a vendor's key: sent once, sealed, never read back. */
export async function keepBoxKey(credentials: Credentials, vendor: string, key: string): Promise<void> {
  await put(credentials, `${OPS}/provider-keys/${named(vendor)}`, { key });
}

export async function dropBoxKey(credentials: Credentials, vendor: string): Promise<void> {
  await drop(credentials, `${OPS}/provider-keys/${named(vendor)}`);
}

// ── the account numbers are bought on ──

const NumbersAccountSchema = z.looseObject({ account_sid: z.string(), label: z.string().nullish() });
export type NumbersAccount = z.infer<typeof NumbersAccountSchema>;

/** The Twilio account every organization's numbers are bought on; null when there is none, and then none are sold. */
export async function readNumbersAccount(credentials: Credentials): Promise<NumbersAccount | null> {
  return orAbsent(read(credentials, `${OPS}/numbers-account`).then((said) => NumbersAccountSchema.parse(said)));
}

/** Kept only when Twilio takes the pair. */
export async function saveNumbersAccount(credentials: Credentials, wanted: { account_sid: string; user: string; secret: string; label: string }): Promise<void> {
  await put(credentials, `${OPS}/numbers-account`, { kind: "twilio", ...wanted });
}

export async function dropNumbersAccount(credentials: Credentials): Promise<void> {
  await drop(credentials, `${OPS}/numbers-account`);
}

// ── the vendors this runtime has ──

const CatalogueSchema = z.looseObject({
  providers: z.array(z.looseObject({ name: z.string(), does: z.array(z.string()), voices_listed: z.boolean().default(false) })),
  /** Models by `stage/vendor`. */
  models: z.record(z.string(), z.array(z.string())).default({}),
  /** By `stage/vendor`, the model that runs when none is named. */
  runs: z.record(z.string(), z.string()).default({}),
});
export type Catalogue = z.infer<typeof CatalogueSchema>;

export async function readCatalogue(credentials: Credentials): Promise<Catalogue> {
  return CatalogueSchema.parse(await read(credentials, "/v1/providers"));
}

// ── the providers row ──

export const STAGES = ["stt", "llm", "tts"] as const;
export type StageName = (typeof STAGES)[number];

/** A vendor and, when not its own default, a model; a default names who takes over, in order. */
export interface Stage {
  vendor: string;
  model?: string | null | undefined;
  fallbacks?: Stage[] | undefined;
}

const StageSchema: z.ZodType<Stage> = z.lazy(() => z.looseObject({ vendor: z.string(), model: z.string().nullish(), fallbacks: z.array(StageSchema).optional() }));

/** What a model costs in US dollars, by the unit it is billed in; a unit left out or null is not billed. */
export const RATE_UNITS = ["input", "output", "cached_input", "cache_creation", "characters", "audio_seconds", "minutes"] as const;
export type RateUnit = (typeof RATE_UNITS)[number];
export type Rate = Partial<Record<RateUnit, number | null>> & { as_of?: string | null };

// The row is written whole: every key the page does not edit (models, offered, listed, lines…) rides along untouched.
const RowSchema = z.looseObject({
  defaults: z.record(z.string(), StageSchema),
  voices: z.record(z.string(), z.string()).default({}),
  tuning: z.record(z.string(), z.unknown()).default({}),
  hints: z.array(z.string()).default([]),
  rates: z.record(z.string(), z.looseObject({})).default({}),
  judge: z.looseObject({ llm: StageSchema, ceiling_usd: z.number() }).nullish(),
  caller: z.looseObject({ ceiling_usd: z.number().nullish(), llm: StageSchema.nullish() }).nullish(),
  embedding: z.looseObject({ vendor: z.string(), model: z.string(), url: z.string().nullish(), dimensions: z.number().nullish() }).nullish(),
  /** A model's name as a person reads it, by `vendor/model`. */
  names: z.record(z.string(), z.string()).optional(),
});

export interface ProvidersRow {
  defaults: Record<string, Stage>;
  voices: Record<string, string>;
  tuning: Record<string, unknown>;
  hints: string[];
  rates: Record<string, Rate>;
  judge?: { llm: Stage; ceiling_usd: number } | null | undefined;
  caller?: { ceiling_usd?: number | null | undefined; llm?: Stage | null | undefined } | null | undefined;
  embedding?: { vendor: string; model: string; url?: string | null | undefined; dimensions?: number | null | undefined } | null | undefined;
  names?: Record<string, string> | undefined;
  [kept: string]: unknown;
}

export async function readProvidersRow(credentials: Credentials): Promise<ProvidersRow> {
  return RowSchema.parse(await read(credentials, `${OPS}/providers`)) as ProvidersRow;
}

/** The row replaced whole; the gateway refuses a vendor not installed or not doing its stage, in a sentence. */
export async function saveProvidersRow(credentials: Credentials, row: ProvidersRow): Promise<ProvidersRow> {
  // A voice nobody picked is left out: an empty voice is a silent call.
  const voices = Object.fromEntries(Object.entries(row.voices).filter(([, voice]) => voice.trim() !== ""));
  return RowSchema.parse(await put(credentials, `${OPS}/providers`, { ...row, voices })) as ProvidersRow;
}
