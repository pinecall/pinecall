/** Operator doors for what the box itself holds: its vendor keys, the Twilio it buys numbers on, admission. */

import { z } from "zod";

import { drop, GatewayError, put, read, type Credentials } from "@pinecall/core/api";

const OPS = "/v1/ops";

// ── vendor keys ─────────────────────────────────────────────────────────────────

/** The vendors the box holds a key for; never a key. */
export async function readBoxVendors(credentials: Credentials): Promise<string[]> {
  return z.looseObject({ vendors: z.array(z.string()) }).parse(await read(credentials, `${OPS}/provider-keys`)).vendors;
}

/** Hold the box's key for a vendor: sent once, never read back. */
export async function setBoxKey(credentials: Credentials, vendor: string, key: string): Promise<void> {
  await put(credentials, `${OPS}/provider-keys/${encodeURIComponent(vendor)}`, { key });
}

export async function dropBoxKey(credentials: Credentials, vendor: string): Promise<void> {
  await drop(credentials, `${OPS}/provider-keys/${encodeURIComponent(vendor)}`);
}

// ── the account the box buys numbers on ─────────────────────────────────────────

const NumbersAccountSchema = z.strictObject({ account_sid: z.string(), label: z.string() });
export type NumbersAccount = z.infer<typeof NumbersAccountSchema>;

/** The Twilio account the box buys numbers on; null when it holds none, and then it sells none. */
export async function readNumbersAccount(credentials: Credentials): Promise<NumbersAccount | null> {
  try {
    return NumbersAccountSchema.parse(await read(credentials, `${OPS}/numbers-account`));
  } catch (refused) {
    if (refused instanceof GatewayError && refused.status === 404) return null;
    throw refused;
  }
}

/** Keep the account: the gateway tries the pair with Twilio before it keeps it. */
export async function saveNumbersAccount(
  credentials: Credentials,
  wanted: { account_sid: string; user: string; secret: string; label: string },
): Promise<void> {
  await put(credentials, `${OPS}/numbers-account`, { kind: "twilio", ...wanted });
}

export async function dropNumbersAccount(credentials: Credentials): Promise<void> {
  await drop(credentials, `${OPS}/numbers-account`);
}

// ── admission ───────────────────────────────────────────────────────────────────

/** One world's limits for a newborn org: each quota by name, the budget, and what the box lends. */
const NewbornQuotasSchema = z.looseObject({ lends: z.array(z.string()).nullish() }).catchall(z.unknown());
export type NewbornQuotas = Record<string, number | string[] | null | undefined>;

const AdmissionSchema = z.strictObject({
  first: z.record(z.string(), NewbornQuotasSchema),
  later: z.record(z.string(), NewbornQuotasSchema).nullable(),
});
export type Admission = { first: Record<string, NewbornQuotas>; later: Record<string, NewbornQuotas> | null };

/** What a newborn org is given in each world: `first` for a person's first org, `later` for any other. */
export async function readAdmission(credentials: Credentials): Promise<Admission> {
  return AdmissionSchema.parse(await read(credentials, `${OPS}/admission`)) as Admission;
}

/** The row replaced whole; the orgs already made keep their quotas. */
export async function saveAdmission(credentials: Credentials, wanted: Admission): Promise<void> {
  await put(credentials, `${OPS}/admission`, wanted);
}
