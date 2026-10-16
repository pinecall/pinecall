/** Operator doors for box settings: Google sign-in, SMTP mail and email branding. */

import { z } from "zod";

import { drop, GatewayError, post, put, read, type Credentials } from "@pinecall/core/api";

const OPS = "/v1/ops";

// 404/405 means an older gateway without this door: return null. Other errors propagate.
async function orAbsent<T>(asking: Promise<T>): Promise<T | null> {
  try {
    return await asking;
  } catch (refused) {
    if (refused instanceof GatewayError && (refused.status === 404 || refused.status === 405)) return null;
    throw refused;
  }
}

// ── sign-in ─────────────────────────────────────────────────────────────────────

const SignInSchema = z.looseObject({
  google: z.looseObject({ configured: z.boolean(), client_id: z.string().nullish(), redirect_uri: z.string().nullish() }),
});
export type SignIn = z.infer<typeof SignInSchema>;

/** Sign-in providers configured on the box; never includes secrets. */
export async function readSignIn(credentials: Credentials): Promise<SignIn | null> {
  return orAbsent(read(credentials, `${OPS}/signin`).then((said) => SignInSchema.parse(said)));
}

/** Configure Google sign-in; the client secret is write-only. */
export async function saveGoogle(credentials: Credentials, wanted: { client_id: string; client_secret: string }): Promise<void> {
  await put(credentials, `${OPS}/signin/google`, wanted);
}

export async function removeGoogle(credentials: Credentials): Promise<void> {
  await drop(credentials, `${OPS}/signin/google`);
}

// ── mail ────────────────────────────────────────────────────────────────────────

export const SECURITIES = ["starttls", "tls", "none"] as const;
export type Security = (typeof SECURITIES)[number];

const MailSchema = z.looseObject({
  configured: z.boolean(),
  // `stored`: saved via this screen; `environment`: PINECALL_SMTP_URL.
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
  /** Write-only; omit to keep the current one. */
  password?: string;
  from: string;
}

export async function readMail(credentials: Credentials): Promise<Mail | null> {
  return orAbsent(read(credentials, `${OPS}/mail`).then((said) => MailSchema.parse(said)));
}

export async function saveMail(credentials: Credentials, wanted: WantedMail): Promise<void> {
  await put(credentials, `${OPS}/mail`, wanted);
}

export async function removeMail(credentials: Credentials): Promise<void> {
  await drop(credentials, `${OPS}/mail`);
}

/** Send a real test email and return the SMTP result (waits for the server). */
export async function testMail(credentials: Credentials, to: string): Promise<{ sent: boolean; error: string | null }> {
  const said = z.looseObject({ sent: z.boolean(), error: z.string().nullish() }).parse(await post(credentials, `${OPS}/mail/test`, { to }));
  return { sent: said.sent, error: said.error ?? null };
}

// ── brand ───────────────────────────────────────────────────────────────────────

const BrandSchema = z.looseObject({ name: z.string().nullish(), logo_url: z.string().nullish(), accent: z.string().nullish() });
export type Brand = z.infer<typeof BrandSchema>;

export async function readBrand(credentials: Credentials): Promise<Brand | null> {
  return orAbsent(read(credentials, `${OPS}/brand`).then((said) => BrandSchema.parse(said)));
}

export async function saveBrand(credentials: Credentials, wanted: { name: string; logo_url: string; accent: string }): Promise<void> {
  await put(credentials, `${OPS}/brand`, wanted);
}
